"""Camada de controle da IA: a única porta de entrada para os modelos (regras, seção 10.3).

A IA RECOMENDA; quem decide é a regra no código e a pessoa. Esta camada garante que:
- cada modelo pode ser DESLIGADO sem parar o sistema (a regra assume: fallback);
- a SAÍDA é validada (lista fechada de rótulos, probabilidade finita em [0, 1]);
- o M1 tem PISO DE SEGURANÇA: se a regra diz CRÍTICA, a prioridade final é CRÍTICA
  (o modelo pode subir a urgência, nunca baixar a de um caso crítico);
- TODA chamada vai para a trilha de auditoria com modelo, versão, entradas, saída,
  confiança, latência e se houve fallback ("mínimo acesso + máximo contexto para
  auditoria", aula 8). As entradas dos modelos não têm dado pessoal (regras 11).

Nenhum método daqui grava no banco, aciona transporte ou gasta o caixa: a camada só
devolve Recomendações. Inventário de agência: docs/governanca/analise-agencia-ia.md.
"""

from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from pathlib import Path

import pandas as pd

from src.data import parametros as P
from src.models import features as F
from src.observabilidade.registro import RegistroAuditavel, Resultado, Trilha
from src.regras.dominio import Armazenamento, Categoria, Prioridade, TipoDoador
from src.regras.prioridade import prioridade_por_regra
from src.regras.validade import em_rota_expressa


class ModeloIA(StrEnum):
    NLP = "nlp"
    PRIORIDADE = "prioridade"
    DESCARTE = "descarte"


class Fonte(StrEnum):
    MODELO = "modelo"
    REGRA = "regra"  # fallback: modelo desligado, ausente, com erro ou saída inválida
    PISO_DE_SEGURANCA = "piso_de_seguranca"


@dataclass(frozen=True)
class Recomendacao:
    valor: object
    fonte: Fonte
    modelo_versao: str | None
    confianca: float | None = None
    motivo_fallback: str | None = None


class Interruptores:
    """Liga/desliga por modelo. Estado em arquivo (sobrevive a reinício) + variável de ambiente
    REDE_ALIMENTA_IA_DESLIGADOS="nlp,descarte" para desligar já no deploy."""

    def __init__(self, arquivo: Path | None = None, registro: RegistroAuditavel | None = None):
        self._arquivo = arquivo
        self._registro = registro
        desligados_env = {m.strip() for m in os.environ.get("REDE_ALIMENTA_IA_DESLIGADOS", "").split(",") if m.strip()}
        self._estado = {m: m.value not in desligados_env for m in ModeloIA}
        if arquivo and arquivo.exists():
            salvo = json.loads(arquivo.read_text(encoding="utf-8"))
            self._estado |= {ModeloIA(k): bool(v) and self._estado[ModeloIA(k)] for k, v in salvo.items()}

    def ligado(self, modelo: ModeloIA) -> bool:
        return self._estado[modelo]

    def definir(self, modelo: ModeloIA, ligado: bool, ator: str, motivo: str) -> None:
        self._estado[modelo] = ligado
        if self._arquivo:
            self._arquivo.parent.mkdir(parents=True, exist_ok=True)
            self._arquivo.write_text(json.dumps({m.value: v for m, v in self._estado.items()}), encoding="utf-8")
        if self._registro:
            self._registro.registrar(Trilha.AUDITORIA, componente="ia.controle",
                                     acao="LIGAR_MODELO" if ligado else "DESLIGAR_MODELO", ator=ator, papel="admin",
                                     recurso=f"modelo:{modelo}", detalhes={"motivo_informado": motivo[:200]})


class ControleIA:
    def __init__(self, *, interruptores: Interruptores, registro: RegistroAuditavel | None = None,
                 m1=None, m1_meta: dict | None = None, m2=None, m2_meta: dict | None = None, nlp=None,
                 nlp_versao: str | None = None):
        self.interruptores = interruptores
        self._registro = registro
        self._m1, self._m1_meta = m1, m1_meta or {}
        self._m2, self._m2_meta = m2, m2_meta or {}
        self._nlp, self._nlp_versao = nlp, nlp_versao

    # ---------- Modelo 1: prioridade ----------
    def prioridade(self, categoria: Categoria, armazenamento: Armazenamento, tipo_doador: TipoDoador,
                   restante: timedelta, peso_kg: float, ator: str, recurso: str | None = None) -> Recomendacao:
        regra = prioridade_por_regra(categoria, armazenamento, restante, peso_kg)
        entradas = {"categoria": str(categoria), "armazenamento": str(armazenamento), "tipo_doador": str(tipo_doador),
                    "horas_restantes": round(restante / timedelta(hours=1), 2), "peso_kg": float(peso_kg),
                    "rota_expressa": em_rota_expressa(categoria, armazenamento)}
        versao = self._m1_meta.get("versao")
        inicio = time.perf_counter()

        if not self.interruptores.ligado(ModeloIA.PRIORIDADE) or self._m1 is None:
            rec = Recomendacao(regra, Fonte.REGRA, None, motivo_fallback="modelo_desligado")
        else:
            try:
                x = pd.DataFrame([entradas])[F.M1_CATEGORICAS + F.M1_NUMERICAS + F.M1_BOOLEANAS]
                previsto = Prioridade(str(self._m1.predict(x)[0]))  # fora da lista fechada -> ValueError
                confianca = float(self._m1.predict_proba(x)[0].max()) if hasattr(self._m1, "predict_proba") else None
                if regra == Prioridade.CRITICA and previsto != Prioridade.CRITICA:
                    rec = Recomendacao(Prioridade.CRITICA, Fonte.PISO_DE_SEGURANCA, versao, confianca,
                                       motivo_fallback=f"modelo_disse_{previsto}")
                else:
                    rec = Recomendacao(previsto, Fonte.MODELO, versao, confianca)
            except Exception as e:  # noqa: BLE001 - qualquer falha do modelo cai na regra
                rec = Recomendacao(regra, Fonte.REGRA, versao, motivo_fallback=f"erro:{type(e).__name__}")
        self._logar("ia.prioridade", "PREDICAO_PRIORIDADE", ator, recurso, entradas, rec, inicio,
                    extra={"prioridade_regra": str(regra)})
        return rec

    # ---------- Modelo 2: risco de descarte ----------
    def risco_descarte(self, entradas: dict, ator: str, recurso: str | None = None) -> Recomendacao:
        """`entradas` = features do M2 (F.M2_*), com a prioridade já decidida acima. Valor = risco alto (bool)."""
        versao = self._m2_meta.get("versao")
        limiar = self._m2_meta.get("limiar")
        inicio = time.perf_counter()
        heuristica = (entradas["horas_restantes"] - P.MARGEM_CONSUMO_HORAS[Categoria(entradas["categoria"])]
                      ) < P.HEURISTICA_RISCO_HORAS

        if not self.interruptores.ligado(ModeloIA.DESCARTE) or self._m2 is None or limiar is None:
            rec = Recomendacao(bool(heuristica), Fonte.REGRA, None, motivo_fallback="modelo_desligado")
        else:
            try:
                colunas = F.M2_CATEGORICAS + F.M2_NUMERICAS + F.M2_BOOLEANAS
                prob = float(self._m2.predict_proba(pd.DataFrame([entradas])[colunas])[0, 1])
                if not (math.isfinite(prob) and 0.0 <= prob <= 1.0):
                    raise ValueError("probabilidade fora de [0, 1]")
                rec = Recomendacao(prob >= limiar, Fonte.MODELO, versao, round(prob, 4))
            except Exception as e:  # noqa: BLE001
                rec = Recomendacao(bool(heuristica), Fonte.REGRA, versao, motivo_fallback=f"erro:{type(e).__name__}")
        self._logar("ia.descarte", "PREDICAO_DESCARTE", ator, recurso, entradas, rec, inicio,
                    extra={"limiar": limiar, "heuristica_v0": bool(heuristica)})
        return rec

    # ---------- NLP: sugestão de categoria ----------
    def sugerir_categoria(self, texto: str, ator: str, recurso: str | None = None) -> Recomendacao | None:
        """None = sem sugestão: o doador escolhe sozinho (modelo desligado ou texto bloqueado)."""
        from src.seguranca.minimizacao import resumo_de_texto

        inicio = time.perf_counter()
        entradas = {"texto_resumo": resumo_de_texto(texto)}  # o texto em si nunca vai para o log
        if not self.interruptores.ligado(ModeloIA.NLP) or self._nlp is None:
            self._logar("ia.nlp", "SUGESTAO_CATEGORIA", ator, recurso, entradas,
                        Recomendacao(None, Fonte.REGRA, None, motivo_fallback="modelo_desligado"), inicio)
            return None
        sugestao = self._nlp.sugerir(texto)
        if sugestao.bloqueado:
            rec = Recomendacao(None, Fonte.REGRA, self._nlp_versao, motivo_fallback="guardrail")
            self._logar("ia.nlp", "SUGESTAO_CATEGORIA", ator, recurso, entradas, rec, inicio,
                        extra={"motivos_guardrail": sugestao.motivos_bloqueio}, resultado=Resultado.NEGADO)
            return None
        rec = Recomendacao({"categoria": sugestao.categoria, "armazenamento": sugestao.armazenamento},
                           Fonte.MODELO, self._nlp_versao, sugestao.confianca_categoria)
        self._logar("ia.nlp", "SUGESTAO_CATEGORIA", ator, recurso, entradas, rec, inicio)
        return rec

    # ---------- log ----------
    def _logar(self, componente, acao, ator, recurso, entradas, rec: Recomendacao, inicio, extra=None,
               resultado: Resultado = Resultado.SUCESSO) -> None:
        if self._registro is None:
            return
        valor = rec.valor
        if isinstance(valor, dict):
            valor = {k: str(v) for k, v in valor.items()}
        elif valor is not None and not isinstance(valor, bool):
            valor = str(valor)
        self._registro.registrar(
            Trilha.AUDITORIA, componente=componente, acao=acao, ator=ator, papel="sistema", recurso=recurso,
            resultado=resultado,
            detalhes={"entradas": entradas, "saida": valor, "fonte": str(rec.fonte), "modelo_versao": rec.modelo_versao,
                      "confianca": rec.confianca, "motivo_fallback": rec.motivo_fallback,
                      "latencia_ms": round((time.perf_counter() - inicio) * 1000, 2), **(extra or {})},
        )

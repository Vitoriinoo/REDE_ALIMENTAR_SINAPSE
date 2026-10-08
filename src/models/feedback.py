"""Ciclo de feedback humano em 4 passos: RLHF adaptado a classificadores (regras, seção 10.4).

RLHF clássico (LLM): pré-treino -> preferências humanas -> modelo de recompensa -> PPO.
Aqui não há LLM, mas a ideia central é a mesma: o humano corrige a IA e a correção
melhora o próximo modelo. Os 4 passos:

1. A IA SUGERE           -> toda sugestão é logada com a versão (src/models/controle.py)
2. O HUMANO CORRIGE      -> `Feedback` (doador corrige categoria, admin corrige prioridade,
                            ONG recusa na inspeção)
3. O FEEDBACK É VALIDADO -> `validar_feedback`: defesa contra ENVENENAMENTO DE DADOS
                            (OWASP LLM04 / MITRE ATLAS AML.T0020)
4. RETREINO COM PORTÃO   -> `portao_de_promocao` + `RegistroDeVersoes` (rollback)

O feedback é a porta pela qual um atacante influencia o modelo: por isso o passo 3 é o
centro deste módulo, e não o retreino.
"""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

import numpy as np

from src.observabilidade.anomalias import Z_ATENCAO, z_robusto

LIMITE_POR_ATOR_DIA = 20
FRACAO_MAXIMA_POR_ATOR = 0.02
COTA_MINIMA_POR_ATOR = 5  # com poucos rótulos, 2% seria zero: ninguém contribuiria
MIN_FEEDBACKS_PARA_PERFIL = 10  # só dá para dizer que alguém "corrige demais" com algum histórico
TOLERANCIA_PROMOCAO = 0.005  # o candidato pode oscilar até 0,5 p.p. abaixo do atual (ruído de amostra)


class TipoFeedback(StrEnum):
    CATEGORIA = "categoria"  # NLP: doador confirmou ou corrigiu a sugestão
    PRIORIDADE = "prioridade"  # M1: admin/triador corrigiu
    INSPECAO = "inspecao"  # M2/qualidade: ONG recusou na porta


@dataclass(frozen=True)
class Feedback:
    ts: datetime
    ator: str  # pseudônimo
    papel: str
    conta_verificada: bool
    tipo: TipoFeedback
    lote_id: str
    modelo_versao: str | None
    sugerido: str
    final: str  # o que o humano decidiu (igual ao sugerido = confirmação)

    @property
    def corrigiu(self) -> bool:
        return self.sugerido != self.final


@dataclass
class ResultadoValidacao:
    aceitos: list[Feedback] = field(default_factory=list)
    rejeitados: list[tuple[Feedback, str]] = field(default_factory=list)
    quarentena: dict[str, str] = field(default_factory=dict)  # ator -> motivo (vai para revisão humana)

    def resumo(self) -> dict:
        return {"aceitos": len(self.aceitos), "rejeitados": dict(Counter(m for _, m in self.rejeitados)),
                "atores_em_quarentena": len(self.quarentena)}


def validar_feedback(feedbacks: list[Feedback]) -> ResultadoValidacao:
    """Passo 3. Ordem: conta verificada -> limite diário -> perfil anômalo -> cota por ator."""
    r = ResultadoValidacao()
    candidatos = []
    por_ator_dia: Counter = Counter()
    for fb in sorted(feedbacks, key=lambda f: f.ts):
        if not fb.conta_verificada:
            r.rejeitados.append((fb, "conta_nao_verificada"))
            continue
        por_ator_dia[(fb.ator, fb.ts.date())] += 1
        if por_ator_dia[(fb.ator, fb.ts.date())] > LIMITE_POR_ATOR_DIA:
            r.rejeitados.append((fb, "limite_diario"))
            continue
        candidatos.append(fb)

    # Perfil anômalo: taxa de correção do ator muito acima da dos pares (mesmo tipo de feedback).
    por_tipo_ator: dict[tuple, list[Feedback]] = defaultdict(list)
    for fb in candidatos:
        por_tipo_ator[(fb.tipo, fb.ator)].append(fb)
    for tipo in {t for t, _ in por_tipo_ator}:
        taxas = {ator: np.mean([f.corrigiu for f in fbs]) for (t, ator), fbs in por_tipo_ator.items()
                 if t == tipo and len(fbs) >= MIN_FEEDBACKS_PARA_PERFIL}
        if len(taxas) < 3:
            continue
        valores = np.array(list(taxas.values()))
        for ator, taxa in taxas.items():
            z, mediana = z_robusto(taxa, valores, piso_mad=0.02)
            if z >= Z_ATENCAO:
                r.quarentena[ator] = f"taxa de correção {taxa:.0%} vs mediana {mediana:.0%} em {tipo} (z={z:.1f})"
    restantes = []
    for fb in candidatos:
        (r.rejeitados.append((fb, "ator_em_quarentena")) if fb.ator in r.quarentena else restantes.append(fb))

    # Cota: nenhum ator responde por mais de 2% dos rótulos novos (mantém os mais antigos).
    cota = max(COTA_MINIMA_POR_ATOR, math.ceil(FRACAO_MAXIMA_POR_ATOR * len(restantes)))
    usados: Counter = Counter()
    for fb in restantes:
        usados[fb.ator] += 1
        (r.aceitos.append(fb) if usados[fb.ator] <= cota else r.rejeitados.append((fb, "cota_do_ator")))
    return r


# --- Passo 4: portão de promoção ------------------------------------------------------------
@dataclass(frozen=True)
class Decisao:
    promover: bool
    motivos: list[str]


def portao_de_promocao(
    metricas_atual: dict,
    metricas_candidato: dict,
    *,
    metrica_principal: str,
    metas_minimas: dict[str, float],
    treinado_por: str,
    aprovado_por: str | None,
    tolerancia: float = TOLERANCIA_PROMOCAO,
) -> Decisao:
    """As métricas DEVEM vir do conjunto de teste FIXO, que nunca recebe feedback.

    Regras: não piorar a métrica principal (além da tolerância), cumprir as metas mínimas
    e ter aprovação de um humano DIFERENTE de quem treinou (segregação de funções).
    """
    motivos = []
    atual, novo = metricas_atual[metrica_principal], metricas_candidato[metrica_principal]
    if novo < atual - tolerancia:
        motivos.append(f"{metrica_principal} piorou: {atual:.4f} -> {novo:.4f}")
    for metrica, minimo in metas_minimas.items():
        if metricas_candidato.get(metrica, -1) < minimo:
            motivos.append(f"{metrica} abaixo da meta ({metricas_candidato.get(metrica)} < {minimo})")
    if aprovado_por is None:
        motivos.append("sem aprovação humana")
    elif aprovado_por == treinado_por:
        motivos.append("quem treinou não pode aprovar (segregação de funções)")
    return Decisao(promover=not motivos, motivos=motivos)


class RegistroDeVersoes:
    """Histórico de versões promovidas de um modelo, com rollback para a anterior."""

    def __init__(self, arquivo: Path):
        self.arquivo = arquivo
        self.versoes: list[dict] = json.loads(arquivo.read_text(encoding="utf-8")) if arquivo.exists() else []

    def _salvar(self) -> None:
        self.arquivo.parent.mkdir(parents=True, exist_ok=True)
        self.arquivo.write_text(json.dumps(self.versoes, indent=2, ensure_ascii=False), encoding="utf-8")

    @property
    def ativa(self) -> dict | None:
        return next((v for v in reversed(self.versoes) if v["status"] == "ativa"), None)

    def promover(self, versao: str, sha256_artefato: str, metricas: dict, decisao: Decisao, aprovado_por: str) -> None:
        if not decisao.promover:
            raise PermissionError(f"Promoção barrada pelo portão: {decisao.motivos}")
        if self.ativa:
            self.ativa["status"] = "aposentada"
        self.versoes.append({"versao": versao, "sha256_artefato": sha256_artefato, "metricas": metricas,
                             "aprovado_por": aprovado_por, "status": "ativa",
                             "promovida_em": datetime.now(timezone.utc).isoformat()})
        self._salvar()

    def rollback(self, motivo: str) -> dict:
        ativa = self.ativa
        anteriores = [v for v in self.versoes if v["status"] == "aposentada"]
        if ativa is None or not anteriores:
            raise RuntimeError("Não há versão anterior para voltar.")
        ativa["status"] = f"revertida: {motivo[:120]}"
        anteriores[-1]["status"] = "ativa"
        self._salvar()
        return anteriores[-1]


def feedback_para_dict(fb: Feedback) -> dict:
    d = asdict(fb)
    d["ts"] = fb.ts.isoformat()
    return d

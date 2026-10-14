"""Serviço de inferência ISOLADO (checklist do professor, item 8).

Só executa os modelos e devolve números. Não tem segredo, não grava nada, não decide nada e,
no Docker Compose, roda numa rede interna sem saída para a internet, com sistema de arquivos
só leitura e usuário sem privilégios. Quem decide (piso de segurança, fallback para a regra,
interruptores, log auditável) é a `ControleIA` na API, que enxerga este serviço como "o modelo".

Entradas validadas por esquema (lista fechada de valores, faixas) antes de chegar ao modelo:
mesmo um chamador interno não é confiável (Zero Trust).

Uso: uvicorn src.inferencia.servico:app --port 8001
"""

from __future__ import annotations

import logging
import math
import os
from contextlib import asynccontextmanager
from typing import Annotated

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.models import features as F
from src.regras.dominio import Armazenamento, Categoria, Prioridade, TipoDoador

log = logging.getLogger("inferencia")
MODELOS: dict = {}

Num = Annotated[float, Field(allow_inf_nan=False, ge=-1e6, le=1e6)]
NumOuNulo = Annotated[float | None, Field(allow_inf_nan=True, default=None)]  # NaN = "sem ONG" (o pipeline imputa)


class _Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EntradaM1(_Entrada):
    categoria: Categoria
    armazenamento: Armazenamento
    tipo_doador: TipoDoador
    horas_restantes: Num
    peso_kg: Annotated[float, Field(gt=0, le=10_000, allow_inf_nan=False)]
    rota_expressa: bool


class EntradaM2(EntradaM1):
    segmento: Annotated[str, Field(pattern=r"^[a-z_]{2,20}$")]
    regiao: Annotated[str, Field(min_length=2, max_length=40)]
    prioridade: Prioridade
    hora: Annotated[float, Field(ge=0, le=23)]
    dia_semana: Annotated[float, Field(ge=0, le=6)]
    n_ongs_compativeis_10km: Annotated[float, Field(ge=0, le=10_000)]
    dist_ong_top_km: NumOuNulo
    n_transportadores_ativos_raio: Annotated[float, Field(ge=0, le=10_000)]
    min_ate_receber_top: NumOuNulo
    n_ongs_impasse: Annotated[float, Field(ge=0, le=10_000)]
    doador_tem_refrigeracao: bool
    fim_de_semana: bool
    feriado: bool
    refrigerado_disponivel: bool
    doador_pode_entregar: bool
    requer_preparo: bool
    doador_aceita_coleta: bool


class EntradaNLP(_Entrada):
    texto: Annotated[str, Field(min_length=1, max_length=2000)]


def carregar() -> None:
    """Carrega os artefatos com verificação de SHA-256 (src/models/artefatos.py)."""
    from src.models.artefatos import carregar_modelo

    if os.environ.get("REDE_ALIMENTA_CARREGAR_MODELOS", "1") != "1":
        return  # testes: sem modelos, a ControleIA usa a regra (fallback)
    for nome, chave in (("modelo_prioridade", "m1"), ("modelo_descarte", "m2")):
        try:
            MODELOS[chave], MODELOS[f"{chave}_meta"] = carregar_modelo(nome)
        except Exception as e:  # noqa: BLE001 - sem modelo, a API cai na regra (fallback)
            log.error("modelo %s indisponível: %s", nome, type(e).__name__)
    if os.environ.get("REDE_ALIMENTA_NLP", "1") == "1":
        try:
            from src.models.nlp import ClassificadorSimilaridade

            MODELOS["nlp"] = ClassificadorSimilaridade()
        except Exception as e:  # noqa: BLE001
            log.error("NLP indisponível: %s", type(e).__name__)


@asynccontextmanager
async def _ciclo(_: FastAPI):
    carregar()
    yield


app = FastAPI(title="Rede Alimenta IA: inferência (interno)", version="2.1", lifespan=_ciclo,
              docs_url=None, redoc_url=None, openapi_url=None)  # interno: sem documentação exposta


def _meta(chave: str) -> dict | None:
    meta = MODELOS.get(f"{chave}_meta")
    return {k: meta.get(k) for k in ("versao", "limiar", "treinado_em", "sha256_artefato")} if meta else None


@app.get("/saude")
def saude() -> dict:
    nlp = MODELOS.get("nlp")
    return {"m1": _meta("m1"), "m2": _meta("m2"),
            "nlp": {"versao": getattr(nlp, "versao", "nlp-similaridade-v1")} if nlp else None}


def _modelo(chave: str):
    m = MODELOS.get(chave)
    if m is None:
        raise HTTPException(503, f"{chave} indisponível")
    return m


@app.post("/m1")
def prever_m1(e: EntradaM1) -> dict:
    m = _modelo("m1")
    x = pd.DataFrame([e.model_dump(mode="json")])[F.M1_CATEGORICAS + F.M1_NUMERICAS + F.M1_BOOLEANAS]
    proba = m.predict_proba(x)[0]
    return {"classe": str(m.predict(x)[0]), "confianca": float(max(proba))}


@app.post("/m2")
def prever_m2(e: EntradaM2) -> dict:
    m = _modelo("m2")
    dados = {k: (math.nan if v is None else v) for k, v in e.model_dump(mode="json").items()}
    x = pd.DataFrame([dados])[F.M2_CATEGORICAS + F.M2_NUMERICAS + F.M2_BOOLEANAS]
    return {"probabilidade": float(m.predict_proba(x)[0, 1])}


@app.post("/nlp")
def sugerir(e: EntradaNLP) -> dict:
    s = _modelo("nlp").sugerir(e.texto)  # o guardrail roda dentro do classificador (regras 4.4)
    return {"bloqueado": s.bloqueado, "motivos_bloqueio": s.motivos_bloqueio,
            "categoria": s.categoria, "confianca_categoria": s.confianca_categoria,
            "armazenamento": s.armazenamento, "confianca_armazenamento": s.confianca_armazenamento}

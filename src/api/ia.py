"""Montagem da `ControleIA` da API: com o serviço de inferência isolado ou com os modelos no processo.

Com `REDE_ALIMENTA_INFERENCIA_URL` (Docker Compose), os modelos ficam no container `inferencia`
e a API usa "procuradores" com a mesma interface do scikit-learn e do NLP (`predict`,
`predict_proba`, `sugerir`). A `ControleIA` não sabe a diferença: interruptores, piso de
segurança, validação da saída, fallback para a regra e log auditável continuam todos na API.
Se o serviço cair ou demorar, a chamada vira exceção e a `ControleIA` cai na regra.

Sem a variável (deploy num único container), os modelos são carregados no próprio processo.
"""

from __future__ import annotations

import logging
import math
import os
from pathlib import Path

import httpx
import numpy as np
import pandas as pd

from src.models.controle import ControleIA, Interruptores
from src.models.nlp import Sugestao
from src.observabilidade.registro import RegistroAuditavel
from src.regras.dominio import Armazenamento, Categoria

log = logging.getLogger("api.ia")
TIMEOUT = httpx.Timeout(5.0, connect=2.0)


class _Remoto:
    def __init__(self, cliente: httpx.Client, rota: str):
        self._cliente, self._rota = cliente, rota

    def _post(self, corpo: dict) -> dict:
        r = self._cliente.post(self._rota, json=corpo)
        r.raise_for_status()
        return r.json()


def _linha(x: pd.DataFrame) -> dict:
    return {k: (None if isinstance(v, float) and math.isnan(v) else (v.item() if hasattr(v, "item") else v))
            for k, v in x.iloc[0].to_dict().items()}


class M1Remoto(_Remoto):
    """predict/predict_proba como no scikit-learn; uma chamada HTTP por linha (memoizada)."""

    classes_ = np.array(["ALTA", "BAIXA", "CRITICA", "MEDIA"])

    def _resposta(self, x: pd.DataFrame) -> dict:
        corpo = _linha(x)
        if getattr(self, "_ultima", (None,))[0] != corpo:
            self._ultima = (corpo, self._post(corpo))
        return self._ultima[1]

    def predict(self, x):
        return np.array([self._resposta(x)["classe"]])

    def predict_proba(self, x):
        return np.array([[self._resposta(x)["confianca"]]])  # a ControleIA só usa o máximo


class M2Remoto(_Remoto):
    def predict_proba(self, x):
        p = float(self._post(_linha(x))["probabilidade"])
        return np.array([[1 - p, p]])


class NLPRemoto(_Remoto):
    def sugerir(self, texto: str) -> Sugestao:
        r = self._post({"texto": texto})
        return Sugestao(
            bloqueado=bool(r["bloqueado"]), motivos_bloqueio=list(r["motivos_bloqueio"]),
            categoria=Categoria(r["categoria"]) if r["categoria"] else None,
            confianca_categoria=r["confianca_categoria"],
            armazenamento=Armazenamento(r["armazenamento"]) if r["armazenamento"] else None,
            confianca_armazenamento=r["confianca_armazenamento"],
        )


def montar_controle(registro: RegistroAuditavel | None, arquivo_interruptores: Path | None) -> tuple[ControleIA, dict]:
    """Devolve (controle, info) — info descreve onde a IA roda, para o /saude e o dashboard."""
    interruptores = Interruptores(arquivo_interruptores, registro)
    url = os.environ.get("REDE_ALIMENTA_INFERENCIA_URL")
    if url:
        cliente = httpx.Client(base_url=url, timeout=TIMEOUT)
        try:
            meta = cliente.get("/saude").json()
        except httpx.HTTPError as e:
            log.error("inferência indisponível no início (%s): a API sobe com fallback para a regra", type(e).__name__)
            meta = {"m1": None, "m2": None, "nlp": None}
        controle = ControleIA(
            interruptores=interruptores, registro=registro,
            m1=M1Remoto(cliente, "/m1") if meta.get("m1") else None, m1_meta=meta.get("m1") or {},
            m2=M2Remoto(cliente, "/m2") if meta.get("m2") else None, m2_meta=meta.get("m2") or {},
            nlp=NLPRemoto(cliente, "/nlp") if meta.get("nlp") else None,
            nlp_versao=(meta.get("nlp") or {}).get("versao"),
        )
        return controle, {"modo": "servico_isolado", "modelos": meta}

    from src.inferencia import servico

    servico.carregar()
    m = servico.MODELOS
    controle = ControleIA(interruptores=interruptores, registro=registro,
                          m1=m.get("m1"), m1_meta=m.get("m1_meta"), m2=m.get("m2"), m2_meta=m.get("m2_meta"),
                          nlp=m.get("nlp"), nlp_versao="nlp-similaridade-v1" if m.get("nlp") else None)
    return controle, {"modo": "mesmo_processo", "modelos": servico.saude()}

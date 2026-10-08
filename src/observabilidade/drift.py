"""Drift das entradas e das saídas dos modelos (regras 10.2; aula 2: "monitoramento de drift e
anomalias como parte da segurança").

PSI (Population Stability Index) entre a distribuição de REFERÊNCIA (dados de treino) e a
ATUAL (janela recente de produção):

    PSI = Σ (atual_i − ref_i) · ln(atual_i / ref_i)

Faixas usuais: < 0,1 estável · 0,1–0,25 atenção · > 0,25 alerta. Drift não prova ataque:
pode ser mudança real (ex.: dezembro tem mais doações). Por isso drift só AVISA; quem
decide retreinar é um humano, pelo portão do ciclo de feedback (regras 10.4).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.observabilidade.anomalias import Nivel

PSI_ATENCAO = 0.10
PSI_ALERTA = 0.25
_EPS = 1e-4


def psi_numerico(referencia, atual, faixas: int = 10) -> float:
    ref = np.asarray(referencia, dtype=float)
    atu = np.asarray(atual, dtype=float)
    ref, atu = ref[~np.isnan(ref)], atu[~np.isnan(atu)]
    cortes = np.unique(np.quantile(ref, np.linspace(0, 1, faixas + 1)))
    cortes[0], cortes[-1] = -np.inf, np.inf
    p_ref = np.histogram(ref, cortes)[0] / len(ref)
    p_atu = np.histogram(atu, cortes)[0] / len(atu)
    return _psi(p_ref, p_atu)


def psi_categorico(referencia, atual) -> float:
    ref, atu = pd.Series(referencia).astype(str), pd.Series(atual).astype(str)
    classes = sorted(set(ref) | set(atu))
    p_ref = ref.value_counts(normalize=True).reindex(classes, fill_value=0).to_numpy()
    p_atu = atu.value_counts(normalize=True).reindex(classes, fill_value=0).to_numpy()
    return _psi(p_ref, p_atu)


def _psi(p_ref: np.ndarray, p_atu: np.ndarray) -> float:
    p_ref, p_atu = np.clip(p_ref, _EPS, None), np.clip(p_atu, _EPS, None)
    return float(np.sum((p_atu - p_ref) * np.log(p_atu / p_ref)))


def nivel_psi(valor: float) -> Nivel:
    return Nivel.ALERTA if valor > PSI_ALERTA else Nivel.ATENCAO if valor >= PSI_ATENCAO else Nivel.NORMAL


def relatorio_drift(referencia: pd.DataFrame, atual: pd.DataFrame, numericas: list[str],
                    categoricas: list[str]) -> dict[str, dict]:
    saida = {}
    for col in numericas:
        v = psi_numerico(referencia[col], atual[col])
        saida[col] = {"psi": round(v, 4), "nivel": nivel_psi(v).name}
    for col in categoricas:
        v = psi_categorico(referencia[col], atual[col])
        saida[col] = {"psi": round(v, 4), "nivel": nivel_psi(v).name}
    return saida

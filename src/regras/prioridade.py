"""Regra de prioridade do lote (regras, seção 5.1).

É a regra de triagem usada para ROTULAR o dataset simulado. O Modelo 1 aprende a
partir desses rótulos com ruído humano; a regra continua disponível como
fallback determinístico e para auditoria.
"""

from __future__ import annotations

from datetime import timedelta

from src.regras.dominio import ORDEM_PRIORIDADE, Armazenamento, Categoria, Prioridade
from src.regras.validade import em_rota_expressa

_h = lambda horas: timedelta(hours=horas)  # noqa: E731
_d = lambda dias: timedelta(days=dias)  # noqa: E731

# (limite CRÍTICA, limite ALTA, limite MÉDIA): abaixo do limite, cai na faixa.
FAIXAS: dict[Categoria, tuple[timedelta, timedelta, timedelta]] = {
    Categoria.PREPARADO: (_h(12), _h(24), _h(48)),  # preparado refrigerado
    Categoria.REFRIGERADO: (_h(24), _h(48), _h(96)),
    Categoria.CONGELADO: (_d(3), _d(7), _d(15)),
    Categoria.HORTIFRUTI: (_h(36), _h(72), _d(5)),
    Categoria.PADARIA: (_h(18), _h(36), _h(72)),
    Categoria.NAO_PERECIVEL: (timedelta(0), _d(15), _d(30)),  # nunca CRÍTICA
}

PESO_VOLUMOSO_KG = 50.0


def subir_nivel(prioridade: Prioridade, niveis: int = 1) -> Prioridade:
    indice = max(0, ORDEM_PRIORIDADE.index(prioridade) - niveis)
    return ORDEM_PRIORIDADE[indice]


def prioridade_por_regra(
    categoria: Categoria,
    armazenamento: Armazenamento,
    validade_restante: timedelta,
    peso_kg: float,
) -> Prioridade:
    if em_rota_expressa(categoria, armazenamento):
        return Prioridade.CRITICA

    critica, alta, media = FAIXAS[categoria]
    if validade_restante < critica:
        prioridade = Prioridade.CRITICA
    elif validade_restante < alta:
        prioridade = Prioridade.ALTA
    elif validade_restante < media:
        prioridade = Prioridade.MEDIA
    else:
        prioridade = Prioridade.BAIXA

    if peso_kg > PESO_VOLUMOSO_KG:
        prioridade = subir_nivel(prioridade)
    return prioridade

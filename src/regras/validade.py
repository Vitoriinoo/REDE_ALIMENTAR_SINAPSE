"""Validade efetiva e validade mínima para aceite (regras, seções 4.2, 4.3 e 7.5).

A validade de itens de cadeia fria é CALCULADA pelo sistema a partir do preparo /
rótulo e do armazenamento: o valor digitado pelo doador é entrada não confiável.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from src.regras.dominio import CADEIA_FRIA, Armazenamento, Categoria

JANELA_AMBIENTE = timedelta(hours=3)
VALIDADE_PREPARADO_REFRIGERADO = timedelta(hours=72)
# Refrigerado DEPOIS de um tempo em ambiente (orientação da rota expressa, 7.5):
# validade mais conservadora que a de quem foi refrigerado desde o preparo.
VALIDADE_APOS_REFRIGERACAO_TARDIA = timedelta(hours=48)

VALIDADE_MINIMA_ROTA_EXPRESSA = timedelta(hours=1, minutes=30)
VALIDADE_MINIMA: dict[Categoria, timedelta] = {
    Categoria.PREPARADO: timedelta(hours=4),
    Categoria.REFRIGERADO: timedelta(hours=12),
    Categoria.CONGELADO: timedelta(hours=24),
    Categoria.HORTIFRUTI: timedelta(hours=24),
    Categoria.PADARIA: timedelta(hours=12),
    Categoria.NAO_PERECIVEL: timedelta(days=7),
}


class LoteRecusado(ValueError):
    """Lote que não pode entrar na plataforma; `motivo` orienta o doador."""

    def __init__(self, motivo: str):
        super().__init__(motivo)
        self.motivo = motivo


def em_rota_expressa(categoria: Categoria, armazenamento: Armazenamento) -> bool:
    """Item de cadeia fria fora da refrigeração tem validade curta: rota expressa (7.5)."""
    return categoria in CADEIA_FRIA and armazenamento == Armazenamento.AMBIENTE


def validade_efetiva(
    categoria: Categoria,
    armazenamento: Armazenamento,
    *,
    preparo: datetime | None = None,
    validade_rotulo: datetime | None = None,
    saida_refrigeracao: datetime | None = None,
    validade_informada: datetime | None = None,
) -> datetime:
    if categoria == Categoria.PREPARADO:
        if preparo is None:
            raise LoteRecusado("Informe a hora do preparo.")
        if armazenamento == Armazenamento.AMBIENTE:
            return preparo + JANELA_AMBIENTE
        return preparo + VALIDADE_PREPARADO_REFRIGERADO

    if categoria in CADEIA_FRIA:  # Refrigerado / Congelado
        if validade_rotulo is None:
            raise LoteRecusado("Informe a validade do rótulo.")
        if armazenamento == Armazenamento.AMBIENTE:
            if saida_refrigeracao is None:
                raise LoteRecusado("Informe desde que horas o item está fora da refrigeração.")
            return min(validade_rotulo, saida_refrigeracao + JANELA_AMBIENTE)
        return validade_rotulo

    if validade_informada is None:
        raise LoteRecusado("Informe a validade.")
    return validade_informada


def validade_apos_refrigeracao(
    categoria: Categoria,
    validade_em_ambiente: datetime,
    momento_refrigeracao: datetime,
    *,
    preparo: datetime | None = None,
    validade_rotulo: datetime | None = None,
) -> datetime:
    """Nova validade de um lote da rota expressa que o doador refrigerou após orientação.

    Só vale se a refrigeração aconteceu DENTRO da janela de ambiente; depois disso o
    alimento já está impróprio e nada o recupera.
    """
    if momento_refrigeracao >= validade_em_ambiente:
        raise LoteRecusado("Refrigerado fora da janela segura em temperatura ambiente: descarte o alimento.")
    if categoria == Categoria.PREPARADO:
        if preparo is None:
            raise LoteRecusado("Informe a hora do preparo.")
        return preparo + VALIDADE_APOS_REFRIGERACAO_TARDIA
    if validade_rotulo is None:
        raise LoteRecusado("Informe a validade do rótulo.")
    return min(validade_rotulo, momento_refrigeracao + VALIDADE_APOS_REFRIGERACAO_TARDIA)


def validade_minima(categoria: Categoria, armazenamento: Armazenamento) -> timedelta:
    if em_rota_expressa(categoria, armazenamento):
        return VALIDADE_MINIMA_ROTA_EXPRESSA
    return VALIDADE_MINIMA[categoria]


def validar_aceite(
    categoria: Categoria, armazenamento: Armazenamento, validade: datetime, agora: datetime
) -> timedelta:
    """Devolve a validade restante ou levanta LoteRecusado se estiver abaixo do mínimo."""
    restante = validade - agora
    minimo = validade_minima(categoria, armazenamento)
    if restante < minimo:
        raise LoteRecusado(
            f"Validade restante ({restante}) abaixo do mínimo para {categoria} ({minimo}). "
            "Oriente o descarte correto ou a compostagem."
        )
    return restante

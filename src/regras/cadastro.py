"""Limites de cadastro do lote que são regra de negócio, não só formato (regras, seção 4.6)."""

from __future__ import annotations

from enum import StrEnum

PESO_MINIMO_KG = 0.5
PESO_REVISAO_ADMIN_KG = 2_000.0  # acima disso, um humano confere antes do matching
PESO_MAXIMO_KG = 10_000.0  # acima disso é erro de digitação: rejeitado no esquema


class DestinoCadastro(StrEnum):
    MATCHING = "MATCHING"
    REVISAO_ADMIN = "REVISAO_ADMIN"


def destino_por_peso(peso_kg: float) -> DestinoCadastro:
    if not PESO_MINIMO_KG <= peso_kg <= PESO_MAXIMO_KG:
        raise ValueError("Peso fora da faixa aceita: deveria ter sido barrado no esquema de entrada.")
    return DestinoCadastro.REVISAO_ADMIN if peso_kg > PESO_REVISAO_ADMIN_KG else DestinoCadastro.MATCHING

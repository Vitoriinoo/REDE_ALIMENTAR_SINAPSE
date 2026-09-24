"""Conversão kg -> refeições (regras, seção 12.1).

Preparado: 420 g = 1 refeição (WRAP/FareShare).
Demais categorias: kcal/kg (TACO 4ª ed., NEPA/UNICAMP, 2011) / 700 kcal (ponto médio da
refeição principal do PAT, Portaria Interministerial nº 66/2006: 600-800 kcal).
"""

from __future__ import annotations

from statistics import mean

from src.regras.dominio import Categoria

GRAMAS_POR_REFEICAO_PREPARADO = 420
KCAL_POR_REFEICAO = 700

# Itens representantes (nº do item na TACO 4ª ed.: kcal por 100 g).
ITENS_TACO: dict[Categoria, dict[str, int]] = {
    Categoria.REFRIGERADO: {
        "448 Iogurte, natural": 51,
        "460 Leite, fermentado": 70,
        "463 Queijo, mozarela": 330,
        "438 Presunto, com capa de gordura": 128,
        "424 Mortadela": 269,
    },
    Categoria.CONGELADO: {
        "327 Carne, bovina, acém, moído, cru": 137,
        "409 Frango, peito, sem pele, cru": 119,
        "399 Frango, coxa, sem pele, crua": 120,
    },
    Categoria.HORTIFRUTI: {
        "182 Banana, prata, crua": 98,
        "222 Maçã, Fuji, com casca, crua": 56,
        "214 Laranja, pêra, crua": 37,
        "157 Tomate, com semente, cru": 15,
        "78 Alface, crespa, crua": 11,
        "92 Batata, inglesa, crua": 64,
        "110 Cenoura, crua": 34,
        "107 Cebola, crua": 39,
    },
    Categoria.PADARIA: {
        "53 Pão, trigo, francês": 300,
        "52 Pão, trigo, forma, integral": 253,
        "51 Pão, milho, forma": 292,
        "16 Bolo, pronto, chocolate": 410,
        "18 Bolo, pronto, milho": 311,
    },
    # Óleo de soja (884 kcal/100 g) fica de fora de propósito: é condimento, e
    # 1 L de óleo não equivale a ~12 refeições.
    Categoria.NAO_PERECIVEL: {
        "4 Arroz, tipo 1, cru": 358,
        "562 Feijão, carioca, cru": 329,
        "40 Macarrão, trigo, cru": 371,
        "35 Farinha, de trigo": 360,
        "492 Açúcar, cristal": 387,
        "319 Sardinha, conserva em óleo": 285,
        "45 Milho, verde, enlatado, drenado": 98,
        "8 Biscoito, doce, maisena": 443,
    },
}


def _refeicoes_por_kg() -> dict[Categoria, float]:
    fatores = {Categoria.PREPARADO: 1000 / GRAMAS_POR_REFEICAO_PREPARADO}
    for categoria, itens in ITENS_TACO.items():
        kcal_por_kg = mean(itens.values()) * 10
        fatores[categoria] = kcal_por_kg / KCAL_POR_REFEICAO
    return fatores


REFEICOES_POR_KG: dict[Categoria, float] = _refeicoes_por_kg()


def refeicoes(categoria: Categoria, peso_kg: float) -> float:
    return peso_kg * REFEICOES_POR_KG[categoria]

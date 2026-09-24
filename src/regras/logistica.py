"""Permissões de doação, matching, transporte e caixa solidário (regras, seções 3, 6, 7 e 9)."""

from __future__ import annotations

from datetime import timedelta
from enum import StrEnum

from src.regras.dominio import CADEIA_FRIA, Armazenamento, Categoria, Prioridade, TipoDoador
from src.regras.validade import em_rota_expressa

# --- Quem pode doar o quê (4.1) -------------------------------------------------
CATEGORIAS_PF = frozenset({Categoria.HORTIFRUTI, Categoria.NAO_PERECIVEL})


def pode_doar(tipo_doador: TipoDoador, categoria: Categoria) -> bool:
    return tipo_doador == TipoDoador.PJ or categoria in CATEGORIAS_PF


# --- Matching Doador x ONG (6.1, 6.2) --------------------------------------------
PESO_PROXIMIDADE = 0.35
PESO_CAPACIDADE = 0.20
PESO_VULNERABILIDADE = 0.30
PESO_COMPATIBILIDADE = 0.15
RAIO_MAXIMO_KM = 20.0

PRAZO_ACEITE_ONG: dict[Prioridade, timedelta] = {
    Prioridade.CRITICA: timedelta(minutes=12),
    Prioridade.ALTA: timedelta(minutes=25),
    Prioridade.MEDIA: timedelta(minutes=75),
    Prioridade.BAIXA: timedelta(hours=5),
}
MAX_RECUSAS_ANTES_DE_ESCALAR = 3


def score_ong(
    distancia_km: float,
    fracao_capacidade_livre: float,
    ipvs_grupo_setor: int,
    serve_refeicao_a_tempo: bool,
) -> float:
    """Score de ranking de uma ONG já filtrada como elegível.

    - proximidade: 1 no mesmo ponto, 0 no raio máximo;
    - vulnerabilidade: grupo IPVS do SETOR da ONG (1..6) normalizado para 0..1;
    - compatibilidade: 1 se a ONG serve refeição antes de o lote vencer, 0,5 caso contrário.
    """
    proximidade = max(0.0, 1.0 - distancia_km / RAIO_MAXIMO_KM)
    capacidade = min(max(fracao_capacidade_livre, 0.0), 1.0)
    vulnerabilidade = (ipvs_grupo_setor - 1) / 5
    compatibilidade = 1.0 if serve_refeicao_a_tempo else 0.5
    return (
        PESO_PROXIMIDADE * proximidade
        + PESO_CAPACIDADE * capacidade
        + PESO_VULNERABILIDADE * vulnerabilidade
        + PESO_COMPATIBILIDADE * compatibilidade
    )


def ong_aceita_categoria(categoria: Categoria, armazenamento: Armazenamento, ong_tem_refrigeracao: bool) -> bool:
    """Item de cadeia fria refrigerado exige ONG com refrigeração.
    Na rota expressa o consumo é imediato, então a exigência não se aplica."""
    if categoria in CADEIA_FRIA and not em_rota_expressa(categoria, armazenamento):
        return ong_tem_refrigeracao
    return True


# --- Transporte (7.2, 7.3, 7.5) -----------------------------------------------------
ESPERA_TRANSPORTE_GRATUITO: dict[Prioridade, timedelta | None] = {
    Prioridade.CRITICA: timedelta(minutes=18),
    Prioridade.ALTA: timedelta(minutes=38),
    Prioridade.MEDIA: timedelta(hours=2, minutes=30),
    Prioridade.BAIXA: None,  # nunca aciona transporte pago
}
TRAJETO_MAX_SEM_REFRIGERACAO = timedelta(minutes=60)
TRAJETO_MAX_ROTA_EXPRESSA = timedelta(minutes=30)


def trajeto_maximo(categoria: Categoria, armazenamento: Armazenamento, veiculo_refrigerado: bool) -> timedelta | None:
    """Duração máxima de trajeto permitida; None = sem limite."""
    if em_rota_expressa(categoria, armazenamento):
        return TRAJETO_MAX_ROTA_EXPRESSA
    if categoria in CADEIA_FRIA and not veiculo_refrigerado:
        return TRAJETO_MAX_SEM_REFRIGERACAO
    return None


def transporte_elegivel(
    categoria: Categoria, armazenamento: Armazenamento, veiculo_refrigerado: bool, trajeto: timedelta
) -> bool:
    limite = trajeto_maximo(categoria, armazenamento, veiculo_refrigerado)
    return limite is None or trajeto <= limite


def pode_acionar_pago(prioridade: Prioridade, espera: timedelta, risco_alto_de_descarte: bool) -> bool:
    """Entregador pago só se nenhuma opção gratuita aceitou no prazo E o risco de descarte é alto."""
    limite = ESPERA_TRANSPORTE_GRATUITO[prioridade]
    return limite is not None and espera >= limite and risco_alto_de_descarte


# --- Caixa solidário (9) ---------------------------------------------------------------
TETO_POR_ENTREGA = 40.0
TETO_DIARIO_POR_ONG = 200.0


class Aprovacao(StrEnum):
    CONFIRMACAO_ONG = "CONFIRMACAO_ONG"
    GESTOR_CAIXA = "GESTOR_CAIXA"  # gestor externo à ONG (segregação de funções)


def aprovacao_necessaria(valor: float, gasto_do_dia_da_ong: float) -> Aprovacao:
    if valor <= TETO_POR_ENTREGA and gasto_do_dia_da_ong + valor <= TETO_DIARIO_POR_ONG:
        return Aprovacao.CONFIRMACAO_ONG
    return Aprovacao.GESTOR_CAIXA

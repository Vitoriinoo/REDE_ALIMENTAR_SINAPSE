"""Permissões de doação, matching, transporte e caixa solidário (regras, seções 3, 6, 7 e 9)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from src.regras.dominio import CADEIA_FRIA, Armazenamento, Categoria, Prioridade, TipoDoador
from src.regras.validade import em_rota_expressa

# --- Quem pode doar o quê (4.1) -------------------------------------------------
# v2.0: CPF só doa alimento não preparado, industrializado e LACRADO (o lacre é
# revalidado no questionário, Q9).
CATEGORIAS_PF = frozenset({Categoria.NAO_PERECIVEL})


def pode_doar(tipo_doador: TipoDoador, categoria: Categoria) -> bool:
    return tipo_doador == TipoDoador.PJ or categoria in CATEGORIAS_PF


# --- Capacidades declaradas pela ONG (6.4) ----------------------------------------
@dataclass(frozen=True)
class PerfilOng:
    categorias_aceitas: frozenset[Categoria]
    tem_refrigeracao: bool
    tem_freezer: bool
    tem_cozinha: bool
    distribui_cestas: bool
    pode_buscar: bool
    abertura_h: float  # janela de recebimento, horas do dia (ex.: 8.0 -> 8:00)
    fechamento_h: float


def categorias_suportadas(tem_refrigeracao: bool, tem_freezer: bool) -> frozenset[Categoria]:
    """O que a estrutura da ONG comporta: ela não pode declarar aceitar além disso."""
    suportadas = set(Categoria) - {Categoria.REFRIGERADO, Categoria.CONGELADO}
    if tem_refrigeracao:
        suportadas.add(Categoria.REFRIGERADO)
        if tem_freezer:
            suportadas.add(Categoria.CONGELADO)
    return frozenset(suportadas)


def motivo_incompatibilidade(
    categoria: Categoria, armazenamento: Armazenamento, requer_preparo: bool, ong: PerfilOng
) -> str | None:
    """Filtros obrigatórios de compatibilidade (6.1, etapa 1). None = compatível.

    Devolver o motivo (e não só False) permite registrar no log por que cada ONG
    ficou fora do ranking.
    """
    if categoria not in ong.categorias_aceitas:
        return "categoria_nao_aceita"
    # Na rota expressa o consumo é imediato: a exigência de frio não se aplica.
    if categoria in CADEIA_FRIA and not em_rota_expressa(categoria, armazenamento):
        if armazenamento == Armazenamento.CONGELADO and not ong.tem_freezer:
            return "sem_freezer"
        if not ong.tem_refrigeracao:
            return "sem_refrigeracao"
    if requer_preparo and not (ong.tem_cozinha or ong.distribui_cestas):
        return "sem_cozinha"
    return None


def ong_aceita_categoria(categoria: Categoria, armazenamento: Armazenamento, ong_tem_refrigeracao: bool) -> bool:
    """Atalho da v1.1 (só refrigeração), mantido para quem só conhece esse atributo."""
    if categoria in CADEIA_FRIA and not em_rota_expressa(categoria, armazenamento):
        return ong_tem_refrigeracao
    return True


# --- Disponibilidade: tempo até a ONG poder receber (6.1) --------------------------
def proxima_abertura(t: datetime, abertura_h: float, fechamento_h: float) -> datetime:
    """Primeiro instante >= t dentro da janela de recebimento [abertura, fechamento)."""
    meia_noite = datetime.combine(t.date(), datetime.min.time(), tzinfo=t.tzinfo)
    abre = meia_noite + timedelta(hours=abertura_h)
    fecha = meia_noite + timedelta(hours=fechamento_h)
    if t < abre:
        return abre
    if t < fecha:
        return t
    return abre + timedelta(days=1)


# Tempo mediano entre o cadastro e a coleta (match + aceite do transporte): sem ele, o
# ranking acha que o lote chega "agora + trajeto" e escolhe ONGs que fecham antes da entrega.
ANTECEDENCIA_OPERACIONAL = timedelta(minutes=30)


def tempo_ate_receber(agora: datetime, trajeto: timedelta, abertura_h: float, fechamento_h: float,
                      antecedencia: timedelta = ANTECEDENCIA_OPERACIONAL) -> timedelta:
    """max(antecedência + trajeto, espera até a janela abrir): a ONG perto que só abre amanhã perde."""
    return proxima_abertura(agora + antecedencia + trajeto, abertura_h, fechamento_h) - agora


# --- Complementaridade busca x entrega (6.6) ----------------------------------------
class Complementaridade(StrEnum):
    COMPLEMENTAR = "complementar"
    SEM_TRANSPORTE = "sem_transporte"  # nenhum dos dois tem: depende da cascata (7.2)
    REDUNDANTE = "redundante"  # os dois têm: gasta o veículo que outro doador precisaria


VALOR_COMPLEMENTARIDADE = {
    Complementaridade.COMPLEMENTAR: 1.0,
    Complementaridade.SEM_TRANSPORTE: 0.5,
    Complementaridade.REDUNDANTE: 0.0,
}


def complementaridade(doador_pode_entregar: bool, ong_pode_buscar: bool) -> Complementaridade:
    if doador_pode_entregar != ong_pode_buscar:
        return Complementaridade.COMPLEMENTAR
    return Complementaridade.REDUNDANTE if doador_pode_entregar else Complementaridade.SEM_TRANSPORTE


# --- Matching Doador x ONG (6.1, 6.2) --------------------------------------------
# Pesos v2.0 (somam 1; o bônus de pedido é somado por fora).
PESO_ACESSO = 0.30
PESO_CAPACIDADE = 0.15
PESO_VULNERABILIDADE = 0.30
PESO_TURNO = 0.10
PESO_COMPLEMENTARIDADE = 0.15
BONUS_PEDIDO_ABERTO = 0.10
# O acesso pontua só o que DIFERE entre as ONGs (trajeto + espera da janela), sem a antecedência,
# que é igual para todas. Vale 0 a partir de 60 min ~ trajeto do raio máximo (20 km) fora do pico:
# a ONG mais distante do raio fica perto de 0, como a "proximidade" da v1.1.
TEMPO_REFERENCIA_ACESSO = timedelta(minutes=60)
RAIO_MAXIMO_KM = 20.0

PRAZO_ACEITE_ONG: dict[Prioridade, timedelta] = {
    Prioridade.CRITICA: timedelta(minutes=12),
    Prioridade.ALTA: timedelta(minutes=25),
    Prioridade.MEDIA: timedelta(minutes=75),
    Prioridade.BAIXA: timedelta(hours=5),
}
MAX_RECUSAS_ANTES_DE_ESCALAR = 3


def score_ong(
    tempo_ate_receber: timedelta,
    fracao_capacidade_livre: float,
    ipvs_grupo_setor: int,
    serve_refeicao_a_tempo: bool,
    complementaridade: Complementaridade = Complementaridade.SEM_TRANSPORTE,
    tem_pedido_aberto: bool = False,
) -> float:
    """Score de ranking de uma ONG que JÁ passou pelos filtros obrigatórios (6.1, etapa 2).

    - acesso: 1 se pode receber logo, 0 a partir de 60 min de trajeto + espera da janela;
    - vulnerabilidade: grupo IPVS do SETOR da ONG (1..6) normalizado para 0..1;
    - turno: 1 se a ONG serve refeição antes de o lote vencer, 0,5 caso contrário;
    - complementaridade e pedido aberto: preferência forte, não proibição (6.5, 6.6). Os dois são
      MULTIPLICADOS pelo acesso: desempatam entre ONGs acessíveis, mas não puxam o lote para longe.
      Somados por inteiro, eles levavam o lote a ONGs com veículo mais distantes (o carro da ONG não
      é refrigerado) e o descarte simulado subia 1 p.p.; multiplicados, o custo cai para ~0,2 p.p.
    """
    variavel = max(tempo_ate_receber - ANTECEDENCIA_OPERACIONAL, timedelta(0))
    acesso = max(0.0, 1.0 - variavel / TEMPO_REFERENCIA_ACESSO)
    capacidade = min(max(fracao_capacidade_livre, 0.0), 1.0)
    vulnerabilidade = (ipvs_grupo_setor - 1) / 5
    turno = 1.0 if serve_refeicao_a_tempo else 0.5
    return (
        PESO_ACESSO * acesso
        + PESO_CAPACIDADE * capacidade
        + PESO_VULNERABILIDADE * vulnerabilidade
        + PESO_TURNO * turno
        + PESO_COMPLEMENTARIDADE * VALOR_COMPLEMENTARIDADE[complementaridade] * acesso
        + (BONUS_PEDIDO_ABERTO * acesso if tem_pedido_aberto else 0.0)
    )


# --- Pedidos da ONG (6.5) ----------------------------------------------------------
PEDIDO_VALIDADE_MAXIMA = timedelta(days=7)
PEDIDOS_ABERTOS_MAXIMO = 3


class PedidoRecusado(ValueError):
    pass


def validar_pedido(kg: float, capacidade_kg_dia: float, validade: timedelta, pedidos_abertos: int) -> None:
    if kg <= 0 or kg > capacidade_kg_dia:
        raise PedidoRecusado("O pedido deve ter entre 0 e a capacidade diária da ONG em kg.")
    if validade <= timedelta(0) or validade > PEDIDO_VALIDADE_MAXIMA:
        raise PedidoRecusado("A validade do pedido deve ser de até 7 dias.")
    if pedidos_abertos >= PEDIDOS_ABERTOS_MAXIMO:
        raise PedidoRecusado("Limite de 3 pedidos abertos atingido: feche ou aguarde um pedido.")


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

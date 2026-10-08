"""Testes das regras de negócio (docs/regras-de-negocio.md). Cada teste cita a seção que protege."""

from datetime import datetime, timedelta

import pytest

from src.regras.dominio import Armazenamento as A
from src.regras.dominio import Categoria as C
from src.regras.dominio import Prioridade as Pr
from src.regras.dominio import TipoDoador
from src.regras.cadastro import DestinoCadastro, destino_por_peso
from src.regras.logistica import (
    Aprovacao,
    Complementaridade,
    PedidoRecusado,
    PerfilOng,
    aprovacao_necessaria,
    categorias_suportadas,
    complementaridade,
    motivo_incompatibilidade,
    ong_aceita_categoria,
    pode_acionar_pago,
    pode_doar,
    proxima_abertura,
    score_ong,
    tempo_ate_receber,
    transporte_elegivel,
    validar_pedido,
)
from src.regras.prioridade import prioridade_por_regra
from src.regras.refeicoes import refeicoes
from src.regras.validade import (
    LoteRecusado,
    em_rota_expressa,
    validade_apos_refrigeracao,
    validade_efetiva,
    validar_aceite,
)

AGORA = datetime(2026, 9, 24, 14, 0)
h = lambda n: timedelta(hours=n)  # noqa: E731
m = lambda n: timedelta(minutes=n)  # noqa: E731


# --- 4.2 Validade efetiva: calculada pelo sistema ------------------------------------------------
def test_preparado_em_ambiente_vence_3h_apos_o_preparo():
    assert validade_efetiva(C.PREPARADO, A.AMBIENTE, preparo=AGORA) == AGORA + h(3)


def test_preparado_refrigerado_vence_72h_apos_o_preparo():
    assert validade_efetiva(C.PREPARADO, A.REFRIGERADO, preparo=AGORA) == AGORA + h(72)


def test_refrigerado_fora_da_geladeira_vale_o_menor_entre_rotulo_e_janela():
    rotulo = AGORA + timedelta(days=5)
    saida = AGORA - h(1)
    assert validade_efetiva(C.REFRIGERADO, A.AMBIENTE, validade_rotulo=rotulo, saida_refrigeracao=saida) == saida + h(3)


def test_validade_digitada_nao_e_aceita_para_preparado_sem_hora_do_preparo():
    with pytest.raises(LoteRecusado):
        validade_efetiva(C.PREPARADO, A.AMBIENTE, validade_informada=AGORA + timedelta(days=2))


# --- 4.3 Validade mínima -------------------------------------------------------------------------
def test_bloqueia_lote_abaixo_da_validade_minima():
    with pytest.raises(LoteRecusado):
        validar_aceite(C.HORTIFRUTI, A.AMBIENTE, AGORA + h(20), AGORA)  # mínimo 24 h


def test_rota_expressa_aceita_com_1h30_restante():
    assert validar_aceite(C.PREPARADO, A.AMBIENTE, AGORA + m(95), AGORA) == m(95)
    with pytest.raises(LoteRecusado):
        validar_aceite(C.PREPARADO, A.AMBIENTE, AGORA + m(80), AGORA)


# --- 5.1 Prioridade --------------------------------------------------------------------------------
def test_rota_expressa_e_sempre_critica():
    assert em_rota_expressa(C.PREPARADO, A.AMBIENTE)
    assert prioridade_por_regra(C.PREPARADO, A.AMBIENTE, h(2.5), 5) == Pr.CRITICA


@pytest.mark.parametrize(("restante", "esperado"), [(h(10), Pr.CRITICA), (h(20), Pr.ALTA), (h(30), Pr.MEDIA), (h(60), Pr.BAIXA)])
def test_faixas_do_preparado_refrigerado(restante, esperado):
    assert prioridade_por_regra(C.PREPARADO, A.REFRIGERADO, restante, 5) == esperado


def test_nao_perecivel_nunca_e_critico():
    assert prioridade_por_regra(C.NAO_PERECIVEL, A.AMBIENTE, timedelta(days=7), 5) == Pr.ALTA


def test_lote_acima_de_50kg_sobe_um_nivel():
    assert prioridade_por_regra(C.HORTIFRUTI, A.AMBIENTE, timedelta(days=4), 30) == Pr.MEDIA
    assert prioridade_por_regra(C.HORTIFRUTI, A.AMBIENTE, timedelta(days=4), 80) == Pr.ALTA


# --- 4.1 Quem pode doar ------------------------------------------------------------------------
@pytest.mark.parametrize("categoria", [C.PREPARADO, C.REFRIGERADO, C.CONGELADO, C.PADARIA, C.HORTIFRUTI])
def test_pessoa_fisica_so_doa_nao_perecivel(categoria):
    """v2.0: CPF só doa alimento não preparado e lacrado (o lacre é a pergunta Q9)."""
    assert not pode_doar(TipoDoador.PF, categoria)
    assert pode_doar(TipoDoador.PJ, categoria)


def test_pessoa_fisica_doa_nao_perecivel():
    assert pode_doar(TipoDoador.PF, C.NAO_PERECIVEL)


# --- 4.6 Peso: faixa de revisão humana ---------------------------------------------------------
def test_lote_acima_de_2_toneladas_vai_para_revisao_do_admin():
    assert destino_por_peso(1_999) == DestinoCadastro.MATCHING
    assert destino_por_peso(2_500) == DestinoCadastro.REVISAO_ADMIN
    with pytest.raises(ValueError):
        destino_por_peso(20_000)


# --- 6.1 Matching -----------------------------------------------------------------------------------
def test_ong_sem_refrigeracao_nao_recebe_refrigerado_exceto_rota_expressa():
    assert not ong_aceita_categoria(C.REFRIGERADO, A.REFRIGERADO, ong_tem_refrigeracao=False)
    assert ong_aceita_categoria(C.PREPARADO, A.AMBIENTE, ong_tem_refrigeracao=False)  # consumo imediato


def test_vulnerabilidade_do_setor_aumenta_o_score():
    base = dict(tempo_ate_receber=m(45), fracao_capacidade_livre=0.5, serve_refeicao_a_tempo=True)
    assert score_ong(ipvs_grupo_setor=6, **base) > score_ong(ipvs_grupo_setor=1, **base)


# --- 6.4 Filtros obrigatórios de compatibilidade ---------------------------------------------------
def _perfil(**kw):
    base = dict(categorias_aceitas=frozenset(C), tem_refrigeracao=True, tem_freezer=True, tem_cozinha=True,
                distribui_cestas=False, pode_buscar=False, abertura_h=8.0, fechamento_h=18.0)
    return PerfilOng(**(base | kw))


def test_ong_sem_cozinha_nao_recebe_alimento_que_requer_preparo():
    assert motivo_incompatibilidade(C.NAO_PERECIVEL, A.AMBIENTE, True, _perfil(tem_cozinha=False)) == "sem_cozinha"
    assert motivo_incompatibilidade(C.NAO_PERECIVEL, A.AMBIENTE, False, _perfil(tem_cozinha=False)) is None


def test_ong_que_distribui_cestas_recebe_alimento_cru_mesmo_sem_cozinha():
    perfil = _perfil(tem_cozinha=False, distribui_cestas=True)
    assert motivo_incompatibilidade(C.NAO_PERECIVEL, A.AMBIENTE, True, perfil) is None


def test_ong_filtra_categorias_que_nao_aceita():
    perfil = _perfil(categorias_aceitas=frozenset({C.NAO_PERECIVEL}))
    assert motivo_incompatibilidade(C.PADARIA, A.AMBIENTE, False, perfil) == "categoria_nao_aceita"


def test_congelado_exige_freezer_e_refrigerado_exige_refrigeracao():
    assert motivo_incompatibilidade(C.CONGELADO, A.CONGELADO, False, _perfil(tem_freezer=False)) == "sem_freezer"
    sem_frio = _perfil(tem_refrigeracao=False, tem_freezer=False)
    assert motivo_incompatibilidade(C.REFRIGERADO, A.REFRIGERADO, False, sem_frio) == "sem_refrigeracao"


def test_estrutura_limita_o_que_a_ong_pode_declarar():
    assert C.REFRIGERADO not in categorias_suportadas(tem_refrigeracao=False, tem_freezer=False)
    assert C.CONGELADO not in categorias_suportadas(tem_refrigeracao=True, tem_freezer=False)
    assert C.CONGELADO in categorias_suportadas(tem_refrigeracao=True, tem_freezer=True)


# --- 6.1 Disponibilidade: tempo até a ONG poder receber ---------------------------------------------
def test_ong_fechada_espera_ate_abrir():
    assert proxima_abertura(datetime(2026, 10, 5, 19, 0), 8, 18) == datetime(2026, 10, 6, 8, 0)
    assert proxima_abertura(datetime(2026, 10, 5, 6, 0), 8, 18) == datetime(2026, 10, 5, 8, 0)
    assert proxima_abertura(AGORA, 8, 18) == AGORA


def test_ong_perto_que_so_abre_amanha_perde_para_ong_longe_aberta():
    fim_de_tarde = datetime(2026, 10, 5, 17, 40)
    perto_fechando = tempo_ate_receber(fim_de_tarde, m(5), 8, 18)  # chegaria 18:15: já fechou, só amanhã
    longe_aberta = tempo_ate_receber(fim_de_tarde, m(35), 13, 22)
    assert perto_fechando > h(14) and longe_aberta == m(30 + 35)
    base = dict(fracao_capacidade_livre=0.5, ipvs_grupo_setor=4, serve_refeicao_a_tempo=True)
    assert score_ong(longe_aberta, **base) > score_ong(perto_fechando, **base)


# --- 6.5 / 6.6 Pedidos e complementaridade ---------------------------------------------------------
def test_complementaridade_busca_x_entrega():
    assert complementaridade(doador_pode_entregar=True, ong_pode_buscar=False) == Complementaridade.COMPLEMENTAR
    assert complementaridade(doador_pode_entregar=False, ong_pode_buscar=True) == Complementaridade.COMPLEMENTAR
    assert complementaridade(doador_pode_entregar=True, ong_pode_buscar=True) == Complementaridade.REDUNDANTE
    assert complementaridade(doador_pode_entregar=False, ong_pode_buscar=False) == Complementaridade.SEM_TRANSPORTE


def test_redundante_e_preferencia_nao_proibicao():
    """A ONG redundante perde pontos, mas continua com score positivo (regras 6.6)."""
    base = dict(tempo_ate_receber=m(40), fracao_capacidade_livre=0.5, ipvs_grupo_setor=4, serve_refeicao_a_tempo=True)
    redundante = score_ong(complementaridade=Complementaridade.REDUNDANTE, **base)
    assert 0 < redundante < score_ong(complementaridade=Complementaridade.COMPLEMENTAR, **base)


def test_complementaridade_nao_puxa_lote_para_longe():
    """Multiplicada pelo acesso: no limite do acesso (30 min + 60 min de trajeto) ela não vale nada."""
    longe = dict(tempo_ate_receber=m(30 + 60), fracao_capacidade_livre=0.5, ipvs_grupo_setor=4,
                 serve_refeicao_a_tempo=True)
    assert score_ong(complementaridade=Complementaridade.COMPLEMENTAR, **longe) == pytest.approx(
        score_ong(complementaridade=Complementaridade.REDUNDANTE, **longe))


def test_pedido_aberto_da_bonus_no_ranking():
    base = dict(tempo_ate_receber=m(40), fracao_capacidade_livre=0.5, ipvs_grupo_setor=4, serve_refeicao_a_tempo=True)
    assert score_ong(tem_pedido_aberto=True, **base) > score_ong(tem_pedido_aberto=False, **base)


def test_limites_do_pedido_da_ong():
    validar_pedido(50, capacidade_kg_dia=80, validade=timedelta(days=7), pedidos_abertos=2)
    with pytest.raises(PedidoRecusado):
        validar_pedido(100, capacidade_kg_dia=80, validade=timedelta(days=3), pedidos_abertos=0)
    with pytest.raises(PedidoRecusado):
        validar_pedido(50, capacidade_kg_dia=80, validade=timedelta(days=8), pedidos_abertos=0)
    with pytest.raises(PedidoRecusado):
        validar_pedido(50, capacidade_kg_dia=80, validade=timedelta(days=3), pedidos_abertos=3)


# --- 7.2 / 7.3 / 7.5 Transporte --------------------------------------------------------------------
def test_cadeia_fria_sem_refrigeracao_limita_trajeto_a_60min():
    assert transporte_elegivel(C.REFRIGERADO, A.REFRIGERADO, veiculo_refrigerado=False, trajeto=m(55))
    assert not transporte_elegivel(C.REFRIGERADO, A.REFRIGERADO, veiculo_refrigerado=False, trajeto=m(70))
    assert transporte_elegivel(C.REFRIGERADO, A.REFRIGERADO, veiculo_refrigerado=True, trajeto=m(120))


def test_rota_expressa_limita_trajeto_a_30min_mesmo_com_refrigeracao():
    assert not transporte_elegivel(C.PREPARADO, A.AMBIENTE, veiculo_refrigerado=True, trajeto=m(40))


def test_prioridade_baixa_nunca_aciona_transporte_pago():
    assert not pode_acionar_pago(Pr.BAIXA, h(10), risco_alto_de_descarte=True)


def test_pago_exige_espera_estourada_e_risco_alto():
    assert not pode_acionar_pago(Pr.CRITICA, m(10), risco_alto_de_descarte=True)
    assert not pode_acionar_pago(Pr.CRITICA, m(20), risco_alto_de_descarte=False)
    assert pode_acionar_pago(Pr.CRITICA, m(20), risco_alto_de_descarte=True)


# --- 9 Caixa solidário (segregação de funções) -----------------------------------------------------
def test_ate_o_teto_a_ong_confirma_acima_o_gestor_aprova():
    assert aprovacao_necessaria(35.0, gasto_do_dia_da_ong=0) == Aprovacao.CONFIRMACAO_ONG
    assert aprovacao_necessaria(45.0, gasto_do_dia_da_ong=0) == Aprovacao.GESTOR_CAIXA
    assert aprovacao_necessaria(35.0, gasto_do_dia_da_ong=180) == Aprovacao.GESTOR_CAIXA  # teto diário R$ 200


# --- 7.5 Orientação de refrigeração -----------------------------------------------------------------
def test_refrigerar_dentro_da_janela_da_48h_a_partir_do_preparo():
    nova = validade_apos_refrigeracao(C.PREPARADO, AGORA + h(2), AGORA, preparo=AGORA - h(1))
    assert nova == AGORA - h(1) + h(48)


def test_refrigerar_fora_da_janela_nao_recupera_o_alimento():
    with pytest.raises(LoteRecusado):
        validade_apos_refrigeracao(C.PREPARADO, AGORA, AGORA + m(10), preparo=AGORA - h(3))


# --- 12.1 Refeições ----------------------------------------------------------------------------------
def test_preparado_usa_420g_por_refeicao():
    assert refeicoes(C.PREPARADO, 4.2) == pytest.approx(10)


def test_hortifruti_rende_menos_refeicoes_por_kg_que_graos():
    assert refeicoes(C.HORTIFRUTI, 1) < refeicoes(C.NAO_PERECIVEL, 1)

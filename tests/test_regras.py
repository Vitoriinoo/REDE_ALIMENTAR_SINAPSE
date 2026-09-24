"""Testes das regras de negócio (docs/regras-de-negocio.md). Cada teste cita a seção que protege."""

from datetime import datetime, timedelta

import pytest

from src.regras.dominio import Armazenamento as A
from src.regras.dominio import Categoria as C
from src.regras.dominio import Prioridade as Pr
from src.regras.dominio import TipoDoador
from src.regras.logistica import (
    Aprovacao,
    aprovacao_necessaria,
    ong_aceita_categoria,
    pode_acionar_pago,
    pode_doar,
    score_ong,
    transporte_elegivel,
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
@pytest.mark.parametrize("categoria", [C.PREPARADO, C.REFRIGERADO, C.CONGELADO, C.PADARIA])
def test_pessoa_fisica_nao_doa_categorias_de_risco_sanitario(categoria):
    assert not pode_doar(TipoDoador.PF, categoria)
    assert pode_doar(TipoDoador.PJ, categoria)


def test_pessoa_fisica_doa_hortifruti_e_nao_perecivel():
    assert pode_doar(TipoDoador.PF, C.HORTIFRUTI) and pode_doar(TipoDoador.PF, C.NAO_PERECIVEL)


# --- 6.1 Matching -----------------------------------------------------------------------------------
def test_ong_sem_refrigeracao_nao_recebe_refrigerado_exceto_rota_expressa():
    assert not ong_aceita_categoria(C.REFRIGERADO, A.REFRIGERADO, ong_tem_refrigeracao=False)
    assert ong_aceita_categoria(C.PREPARADO, A.AMBIENTE, ong_tem_refrigeracao=False)  # consumo imediato


def test_vulnerabilidade_do_setor_aumenta_o_score():
    base = dict(distancia_km=5, fracao_capacidade_livre=0.5, serve_refeicao_a_tempo=True)
    assert score_ong(ipvs_grupo_setor=6, **base) > score_ong(ipvs_grupo_setor=1, **base)


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

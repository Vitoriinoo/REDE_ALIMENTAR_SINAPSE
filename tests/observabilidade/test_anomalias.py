"""Observabilidade (regras 10.2): alertar no desvio, antes do teto; freio só para segurança."""

from datetime import datetime, timedelta, timezone

import numpy as np

from src.observabilidade.anomalias import Monitor, Nivel
from src.observabilidade.drift import nivel_psi, psi_categorico, psi_numerico
from src.observabilidade.freio import LIMITE_FREADO_POR_MIN, LIMITE_NORMAL_POR_MIN, Freio

INICIO = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)


def _historico(monitor, sinal, chave, valores, passo=timedelta(days=1)):
    for i, v in enumerate(valores):
        monitor.medir(sinal, chave, INICIO + i * passo, v)


def test_aquecendo_so_o_teto_vale():
    m = Monitor()
    assert m.medir("cadastros_por_dia", "doador:a", INICIO, 40) is None  # sem histórico, sem teto: não alerta


def test_desvio_do_proprio_historico_gera_alerta_antes_de_qualquer_teto():
    m = Monitor()
    _historico(m, "cadastros_por_dia", "doador:a", [2, 3, 2, 1, 3, 2, 2, 3, 2, 1])
    assert m.medir("cadastros_por_dia", "doador:a", INICIO + timedelta(days=11), 3) is None
    alerta = m.medir("cadastros_por_dia", "doador:a", INICIO + timedelta(days=12), 9)
    assert alerta is not None and alerta.nivel == Nivel.ATENCAO
    assert m.medir("cadastros_por_dia", "doador:a", INICIO + timedelta(days=13), 30).nivel == Nivel.ALERTA


def test_o_normal_e_por_chave():
    """30 cadastros/dia é normal para um mercado grande e anômalo para um doador pequeno."""
    m = Monitor()
    _historico(m, "cadastros_por_dia", "doador:grande", [28, 30, 31, 29, 30, 32, 27, 30])
    _historico(m, "cadastros_por_dia", "doador:pequeno", [1, 2, 1, 1, 2, 1, 2, 1])
    dia = INICIO + timedelta(days=20)
    assert m.medir("cadastros_por_dia", "doador:grande", dia, 31) is None
    assert m.medir("cadastros_por_dia", "doador:pequeno", dia, 31) is not None


def test_aproximar_do_teto_avisa_antes_de_bater():
    m = Monitor()
    dia = INICIO
    assert m.medir("gasto_caixa_dia", "ong:x", dia, 100) is None
    assert m.medir("gasto_caixa_dia", "ong:y", dia, 150).nivel == Nivel.ATENCAO  # 75% do teto de R$ 200
    assert m.medir("gasto_caixa_dia", "ong:z", dia, 185).nivel == Nivel.ALERTA
    assert m.medir("gasto_caixa_dia", "ong:w", dia, 200).nivel == Nivel.CRITICO


def test_ataque_nao_e_aprendido_como_normal():
    m = Monitor()
    _historico(m, "cadastros_por_dia", "doador:a", [2, 3, 2, 1, 3, 2, 2, 3])
    for i in range(10):  # ataque sustentado
        assert m.medir("cadastros_por_dia", "doador:a", INICIO + timedelta(days=10 + i), 60).nivel >= Nivel.ALERTA


def test_rajada_de_requisicoes_aciona_o_freio_e_o_freio_expira():
    freio = Freio()
    m = Monitor(freio=freio)
    ip = "ip:abc"
    # linha de base: ~5 requisições por minuto ao longo de 20 minutos
    for minuto in range(20):
        for s in range(5):
            m.contar("requisicoes_por_minuto", ip, INICIO + timedelta(minutes=minuto, seconds=s * 10))
    rajada = INICIO + timedelta(minutes=30)
    alertas = [m.contar("requisicoes_por_minuto", ip, rajada + timedelta(milliseconds=200 * i)) for i in range(80)]
    assert any(a and a.nivel >= Nivel.ALERTA for a in alertas)
    assert freio.ativo(ip, rajada + timedelta(seconds=30))
    assert freio.limite(ip, rajada + timedelta(seconds=30)) == LIMITE_FREADO_POR_MIN
    assert freio.limite(ip, rajada + timedelta(minutes=16)) == LIMITE_NORMAL_POR_MIN  # reversível: expirou


def test_sinal_de_negocio_nunca_freia():
    freio = Freio()
    m = Monitor(freio=freio)
    _historico(m, "cadastros_por_dia", "doador:a", [2, 3, 2, 1, 3, 2, 2, 3])
    m.medir("cadastros_por_dia", "doador:a", INICIO + timedelta(days=30), 80)
    assert not freio.ativo("doador:a", INICIO + timedelta(days=30))


def test_limite_de_requisicoes_e_o_teto():
    freio = Freio()
    permitidas = sum(freio.permitir("ip:x", INICIO + timedelta(milliseconds=i)) for i in range(200))
    assert permitidas == LIMITE_NORMAL_POR_MIN


def test_psi_detecta_drift_e_ignora_amostra_igual():
    rng = np.random.default_rng(0)
    ref = rng.normal(24, 6, 5000)
    assert nivel_psi(psi_numerico(ref, rng.normal(24, 6, 2000))) == Nivel.NORMAL
    assert nivel_psi(psi_numerico(ref, rng.normal(40, 6, 2000))) == Nivel.ALERTA
    assert psi_categorico(["a"] * 50 + ["b"] * 50, ["a"] * 90 + ["b"] * 10) > 0.25

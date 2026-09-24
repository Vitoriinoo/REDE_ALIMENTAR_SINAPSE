"""Testes do guardrail de entrada (aula 4: filtro de entrada; aula 9: evidência e reteste).

O conjunto B de ataques inéditos NÃO é testado aqui como "deve bloquear": ele mede a
generalização e o resultado (risco residual) fica documentado em reports/avaliacao_nlp.json
e na Matriz STRIDE.
"""

import pytest

from src.seguranca.guardrails import TAMANHO_MAXIMO, filtrar_entrada
from src.data.textos import ADVERSARIAIS
from tests.seguranca.ataques_ineditos import BENIGNOS_SUSPEITOS, CONJUNTO_A

PAYLOADS_DATASET = [p for lista in ADVERSARIAIS.values() for p in lista]


@pytest.mark.parametrize("payload", PAYLOADS_DATASET)
def test_bloqueia_payloads_conhecidos(payload):
    assert filtrar_entrada(payload).bloqueado


@pytest.mark.parametrize("payload", CONJUNTO_A)
def test_bloqueia_conjunto_a_apos_mitigacao(payload):
    assert filtrar_entrada(payload).bloqueado


@pytest.mark.parametrize("texto", BENIGNOS_SUSPEITOS)
def test_nao_bloqueia_texto_legitimo_parecido_com_ataque(texto):
    assert not filtrar_entrada(texto).bloqueado


def test_trunca_e_limpa_html_da_saida():
    resultado = filtrar_entrada("<b>30 marmitas</b>" + " x" * TAMANHO_MAXIMO)
    assert "<b>" not in resultado.texto
    assert len(resultado.texto) <= TAMANHO_MAXIMO
    assert "entrada_gigante" in resultado.motivos


def test_remove_caracteres_invisiveis():
    assert filtrar_entrada("10​ pães").texto == "10 pães"

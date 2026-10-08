"""Dígito verificador de CPF e CNPJ, inclusive o CNPJ alfanumérico (regras 6.3)."""

import pytest

from src.validacao.documentos import cnpj_valido, cpf_valido, dv_cnpj, normalizar


def test_exemplo_oficial_do_cnpj_alfanumerico():
    """Exemplo divulgado pela Receita Federal para o novo formato (IN RFB 2.229/2024)."""
    assert dv_cnpj("12ABC34501DE") == "35"
    assert cnpj_valido("12.ABC.345/01DE-35")


def test_cnpj_numerico_antigo_continua_valido():
    assert cnpj_valido("11.222.333/0001-81")
    assert cnpj_valido("11222333000181")


@pytest.mark.parametrize("cnpj", [
    "11.222.333/0001-82",  # dígito errado
    "12.ABC.345/01DE-36",
    "00000000000000",  # todos iguais: passa no módulo 11, mas é inválido
    "12.ABC.345/01DE-3A",  # dígito verificador tem de ser numérico
    "11.222.333/0001",  # curto
    "11.222.333/0001-81; DROP TABLE",
])
def test_cnpj_invalido(cnpj):
    assert not cnpj_valido(cnpj)


def test_minusculas_sao_normalizadas():
    assert normalizar("12.abc.345/01de-35") == "12ABC34501DE35"
    assert cnpj_valido("12.abc.345/01de-35")


def test_cpf():
    assert cpf_valido("529.982.247-25")
    assert not cpf_valido("529.982.247-26")
    assert not cpf_valido("111.111.111-11")
    assert not cpf_valido("5299822472A")

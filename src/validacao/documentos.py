"""Dígito verificador de CPF e CNPJ (regras, seções 4.6 e 6.3).

O dígito verificador prova só que o número PODE existir: pega erro de digitação e
número inventado ao acaso. Quem prova que o CNPJ existe e está ativo é a consulta à
Receita (src/validacao/receita.py); quem prova a legitimidade da entidade é o admin.

CNPJ alfanumérico (IN RFB nº 2.229/2024, vigente desde julho/2026): as 12 primeiras
posições aceitam letras A-Z e dígitos; os 2 dígitos verificadores continuam numéricos.
O cálculo é o mesmo módulo 11 de sempre, com cada caractere valendo (código ASCII - 48):
'0'..'9' = 0..9 e 'A'..'Z' = 17..42. Assim os CNPJs numéricos antigos continuam válidos.
"""

from __future__ import annotations

import re

_SEPARADORES = re.compile(r"[.\-/\s]")
_FORMATO_CNPJ = re.compile(r"[0-9A-Z]{12}[0-9]{2}")
_FORMATO_CPF = re.compile(r"[0-9]{11}")

_PESOS_CNPJ_DV1 = (5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)
_PESOS_CNPJ_DV2 = (6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2)


def normalizar(documento: str) -> str:
    """Remove a máscara (pontos, barra, hífen, espaços) e põe em maiúsculas."""
    return _SEPARADORES.sub("", documento).upper()


def _dv_modulo11(valores: list[int], pesos: tuple[int, ...]) -> int:
    resto = sum(v * p for v, p in zip(valores, pesos, strict=True)) % 11
    return 0 if resto < 2 else 11 - resto


def dv_cnpj(base12: str) -> str:
    """Calcula os 2 dígitos verificadores das 12 primeiras posições do CNPJ."""
    valores = [ord(c) - 48 for c in base12]
    dv1 = _dv_modulo11(valores, _PESOS_CNPJ_DV1)
    dv2 = _dv_modulo11(valores + [dv1], _PESOS_CNPJ_DV2)
    return f"{dv1}{dv2}"


def cnpj_valido(cnpj: str) -> bool:
    c = normalizar(cnpj)
    if not _FORMATO_CNPJ.fullmatch(c) or len(set(c)) == 1:
        return False
    return dv_cnpj(c[:12]) == c[12:]


def cpf_valido(cpf: str) -> bool:
    c = normalizar(cpf)
    if not _FORMATO_CPF.fullmatch(c) or len(set(c)) == 1:
        return False
    digitos = [int(d) for d in c]
    for n in (9, 10):  # 1º DV usa pesos 10..2, 2º DV usa 11..2
        resto = sum(d * p for d, p in zip(digitos[:n], range(n + 1, 1, -1))) % 11
        if digitos[n] != (0 if resto < 2 else 11 - resto):
            return False
    return True

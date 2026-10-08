"""Leitura de segredos (chaves HMAC, chave de assinatura) a partir do ambiente.

Em produção (`REDE_ALIMENTA_AMBIENTE=producao`) todo segredo é OBRIGATÓRIO: a aplicação
não sobe com valor padrão. Em desenvolvimento e nos testes existe um valor padrão
explícito, que só serve para dados sintéticos.
"""

from __future__ import annotations

import os


class SegredoAusente(RuntimeError):
    pass


def em_producao() -> bool:
    return os.environ.get("REDE_ALIMENTA_AMBIENTE", "desenvolvimento") == "producao"


def obter_segredo(nome: str, padrao_desenvolvimento: str) -> bytes:
    valor = os.environ.get(nome)
    if valor:
        return valor.encode()
    if em_producao():
        raise SegredoAusente(f"Segredo {nome} não configurado: configure no cofre de segredos.")
    return padrao_desenvolvimento.encode()

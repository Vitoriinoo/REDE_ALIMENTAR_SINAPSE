"""Autenticação por chave de API (cabeçalho `X-Chave-API`) e autorização por papel.

- O **tipo do doador, o papel e o ID vêm da conta autenticada**, nunca do corpo da requisição.
  Assim, um doador PF não consegue se passar por PJ mandando `"tipo": "PJ"` (revisão do
  checklist, item 1).
- O servidor guarda só o **SHA-256 da chave** (`REDE_ALIMENTA_CHAVES_API`, JSON
  `{"<sha256>": {"papel": "doador", "id": "D-0008"}}`). Quem lê a variável não obtém as chaves.
  Gerar: `python -m src.api.chaves` (as chaves em claro vão para `segredos/`, fora do Git).
- Em desenvolvimento (e só nele), aceita chaves `dev:<papel>:<id>` para testes e demonstração local.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass
from enum import StrEnum

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from src.seguranca.segredos import em_producao


class Papel(StrEnum):
    DOADOR = "doador"
    ONG = "ong"
    ADMIN = "admin"


@dataclass(frozen=True)
class Identidade:
    papel: Papel
    id: str

    @property
    def ator(self) -> str:
        return f"{self.papel}:{self.id}"


_ID = re.compile(r"^(D-\d{4}|O-\d{3}|A-\d{2})$")
_cabecalho = APIKeyHeader(name="X-Chave-API", auto_error=False, description="Chave de API do usuário")


def _cadastro_de_chaves() -> dict[str, dict]:
    bruto = os.environ.get("REDE_ALIMENTA_CHAVES_API", "")
    return json.loads(bruto) if bruto else {}


def identificar(chave: str | None) -> Identidade | None:
    if not chave or len(chave) > 200:
        return None
    resumo = hashlib.sha256(chave.encode()).hexdigest()
    for h, ident in _cadastro_de_chaves().items():
        if hmac.compare_digest(h, resumo):  # comparação em tempo constante
            return Identidade(Papel(ident["papel"]), ident["id"])
    if not em_producao() and chave.startswith("dev:"):
        partes = chave.split(":")
        if len(partes) == 3 and partes[1] in Papel.__members__.values() and _ID.match(partes[2]):
            return Identidade(Papel(partes[1]), partes[2])
    return None


def autenticado(chave: str | None = Security(_cabecalho)) -> Identidade:
    ident = identificar(chave)
    if ident is None:
        raise HTTPException(401, "chave de API ausente ou inválida", headers={"WWW-Authenticate": "ApiKey"})
    return ident


def exige(*papeis: Papel):
    def _verificar(ident: Identidade = Depends(autenticado)) -> Identidade:
        if ident.papel not in papeis:
            raise HTTPException(403, "papel sem permissão para esta ação")
        return ident

    return _verificar

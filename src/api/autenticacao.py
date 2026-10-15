"""Autenticação (token de sessão do login ou chave de API) e autorização por papel.

- Login com e-mail e senha (`POST /v1/auth/login`) devolve um token `ras_...` assinado com HMAC
  (src/seguranca/senhas.py). Ele vale como `Authorization: Bearer ras_...` ou em `X-Chave-API`.
- As chaves de API continuam valendo (testes e integração).

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
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from src.seguranca.senhas import PREFIXO_TOKEN, ler_token
from src.seguranca.segredos import em_producao


class Papel(StrEnum):
    DOADOR = "doador"
    ONG = "ong"
    TRANSPORTADOR = "transportador"
    ADMIN = "admin"


@dataclass(frozen=True)
class Identidade:
    papel: Papel
    id: str

    @property
    def ator(self) -> str:
        return f"{self.papel}:{self.id}"


_ID = re.compile(r"^(D-\d{4}|O-\d{3}|V-\d{3}|A-\d{2})$")
_cabecalho = APIKeyHeader(name="X-Chave-API", auto_error=False, description="Chave de API ou token de sessão")
_portador = HTTPBearer(auto_error=False, description="Token de sessão `ras_...` devolvido por /v1/auth/login")


def _cadastro_de_chaves() -> dict[str, dict]:
    bruto = os.environ.get("REDE_ALIMENTA_CHAVES_API", "")
    return json.loads(bruto) if bruto else {}


def identificar(chave: str | None) -> Identidade | None:
    if not chave or len(chave) > 500:
        return None
    if chave.startswith(PREFIXO_TOKEN):
        dados = ler_token(chave)
        if dados and dados["papel"] in Papel.__members__.values() and isinstance(dados["id"], str):
            return Identidade(Papel(dados["papel"]), dados["id"])
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


def credencial(chave: str | None, autorizacao: str | None) -> str | None:
    """O que veio na requisição: `X-Chave-API` ou o token de `Authorization: Bearer`."""
    if chave:
        return chave
    if autorizacao and autorizacao[:7].lower() == "bearer ":
        return autorizacao[7:].strip()
    return None


def autenticado(chave: str | None = Security(_cabecalho),
                portador: HTTPAuthorizationCredentials | None = Security(_portador)) -> Identidade:
    ident = identificar(chave or (portador.credentials if portador else None))
    if ident is None:
        raise HTTPException(401, "credencial ausente ou inválida", headers={"WWW-Authenticate": "Bearer"})
    return ident


def exige(*papeis: Papel):
    def _verificar(ident: Identidade = Depends(autenticado)) -> Identidade:
        if ident.papel not in papeis:
            raise HTTPException(403, "papel sem permissão para esta ação")
        return ident

    return _verificar

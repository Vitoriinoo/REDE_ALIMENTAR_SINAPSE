"""Minimização de dados pessoais em logs e documentos (regras 10.1 e 11; aula 6, controle C5).

"Logs completos" com dados pessoais são um RISCO (aula 6). Por isso a minimização é
aplicada no código, antes de gravar, e não depende de quem escreve o log lembrar:
- pseudônimo: o ator aparece como HMAC do identificador (sem a chave, não se reverte);
- chaves proibidas são removidas;
- valores com cara de CPF, CNPJ, e-mail, telefone ou CEP são mascarados.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from typing import Any

from src.seguranca.segredos import obter_segredo

CHAVES_PROIBIDAS = frozenset({
    "cpf", "cnpj", "documento", "nome", "razao_social", "email", "telefone", "endereco", "logradouro",
    "cep", "lat", "lon", "latitude", "longitude", "texto", "descricao", "senha", "token", "authorization",
    "cookie", "chave", "segredo", "qsa", "ip",
})

_PADROES = [
    ("[EMAIL]", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")),
    ("[CNPJ]", re.compile(r"\b[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?[0-9]{2}\b")),
    ("[CPF]", re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")),
    ("[TELEFONE]", re.compile(r"(?:\+?55\s?)?\(?\b\d{2}\)?\s?9?\d{4}[-\s]?\d{4}\b")),
    ("[CEP]", re.compile(r"\b\d{5}-\d{3}\b")),
]


def pseudonimo(tipo: str, identificador: str) -> str:
    """Ex.: pseudonimo("doador", "D-0001") -> "doador:3f9a1c…". Estável para a mesma chave."""
    chave = obter_segredo("REDE_ALIMENTA_CHAVE_PSEUDONIMO", "dev-pseudonimo-somente-dados-sinteticos")
    return f"{tipo}:{hmac.new(chave, identificador.encode(), hashlib.sha256).hexdigest()[:16]}"


def mascarar_texto(texto: str) -> str:
    for rotulo, padrao in _PADROES:
        texto = padrao.sub(rotulo, texto)
    return texto


def minimizar(valor: Any) -> Any:
    """Cópia do valor sem chaves proibidas e com dados pessoais mascarados (recursivo)."""
    if isinstance(valor, dict):
        return {k: minimizar(v) for k, v in valor.items() if str(k).lower() not in CHAVES_PROIBIDAS}
    if isinstance(valor, (list, tuple)):
        return [minimizar(v) for v in valor]
    if isinstance(valor, str):
        return mascarar_texto(valor)
    return valor


def resumo_de_texto(texto: str) -> dict:
    """O que pode ir para o log sobre um texto livre: nunca o texto, só hash e tamanho."""
    return {"sha256": hashlib.sha256(texto.encode()).hexdigest(), "tamanho": len(texto)}

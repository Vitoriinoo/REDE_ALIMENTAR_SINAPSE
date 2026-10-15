"""Senhas, identificadores pessoais e token de sessão do login real (PLANO-TELAS, decisão 2).

- Senha: scrypt (hashlib, sem dependência nova) com sal aleatório. Guarda-se só
  `scrypt$n$r$p$sal$hash`; a conferência é em tempo constante.
- CPF/CNPJ e e-mail: só HMAC-SHA256 com `REDE_ALIMENTA_CHAVE_HMAC` (regras 11, LGPD). O login
  procura a conta pelo HMAC do e-mail, então o banco não guarda nenhum dos dois em claro.
- Token de sessão: `ras_<corpo>.<assinatura>`, com corpo = papel, id e expiração, e assinatura
  HMAC-SHA256 com uma subchave derivada da mesma chave (separação de domínio: o HMAC de um
  documento nunca vale como assinatura de token). Sem estado no servidor; expira em 8 h.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from src.seguranca.segredos import obter_segredo
from src.validacao.documentos import normalizar

PREFIXO_TOKEN = "ras_"
VALIDADE_TOKEN = timedelta(hours=8)
# scrypt: n=2^14, r=8, p=1 (≈16 MB de memória por tentativa), o parâmetro interativo recomendado.
_N, _R, _P, _TAMANHO = 2**14, 8, 1, 32


def _chave() -> bytes:
    return obter_segredo("REDE_ALIMENTA_CHAVE_HMAC", "somente-dados-sinteticos")


def _b64(dados: bytes) -> str:
    return base64.urlsafe_b64encode(dados).rstrip(b"=").decode()


def _de_b64(texto: str) -> bytes:
    return base64.urlsafe_b64decode(texto + "=" * (-len(texto) % 4))


# --- Senha ------------------------------------------------------------------------------------
def gerar_hash(senha: str) -> str:
    sal = secrets.token_bytes(16)
    h = hashlib.scrypt(senha.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=_TAMANHO)
    return f"scrypt${_N}${_R}${_P}${_b64(sal)}${_b64(h)}"


def conferir(senha: str, guardado: str) -> bool:
    try:
        nome, n, r, p, sal, h = guardado.split("$")
        if nome != "scrypt":
            return False
        calculado = hashlib.scrypt(senha.encode(), salt=_de_b64(sal), n=int(n), r=int(r), p=int(p),
                                   dklen=len(_de_b64(h)), maxmem=64 * 1024 * 1024)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, _de_b64(h))


# --- Identificadores pessoais ------------------------------------------------------------------
def hmac_documento(documento: str) -> str:
    return hmac.new(_chave(), normalizar(documento).encode(), hashlib.sha256).hexdigest()


def hmac_email(email: str) -> str:
    return hmac.new(_chave(), b"email:" + email.strip().lower().encode(), hashlib.sha256).hexdigest()


# --- Token de sessão ---------------------------------------------------------------------------
def _chave_token() -> bytes:
    return hmac.new(_chave(), b"token-sessao-v1", hashlib.sha256).digest()


def _assinar(corpo: str) -> str:
    return _b64(hmac.new(_chave_token(), corpo.encode(), hashlib.sha256).digest())


def emitir_token(papel: str, id_: str, agora: datetime | None = None) -> tuple[str, datetime]:
    agora = agora or datetime.now(timezone.utc)
    expira = agora + VALIDADE_TOKEN
    corpo = _b64(json.dumps({"p": papel, "i": id_, "e": int(expira.timestamp())}, separators=(",", ":")).encode())
    return f"{PREFIXO_TOKEN}{corpo}.{_assinar(corpo)}", expira


def ler_token(token: str, agora: datetime | None = None) -> dict | None:
    """{"papel", "id"} se a assinatura confere e o token não expirou; senão None."""
    if not token.startswith(PREFIXO_TOKEN) or len(token) > 500:
        return None
    try:
        corpo, assinatura = token.removeprefix(PREFIXO_TOKEN).split(".")
        if not hmac.compare_digest(assinatura, _assinar(corpo)):
            return None
        dados = json.loads(_de_b64(corpo))
    except (ValueError, TypeError):
        return None
    agora = agora or datetime.now(timezone.utc)
    if not isinstance(dados, dict) or agora.timestamp() > dados.get("e", 0):
        return None
    return {"papel": dados.get("p"), "id": dados.get("i")}

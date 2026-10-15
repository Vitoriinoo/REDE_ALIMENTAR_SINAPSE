"""Gera um .env com segredos novos (HMAC, chave RSA da declaração, chaves de API) para o Compose.

Os valores vão SÓ para arquivos fora do Git (`.env`, `segredos/`), nunca para a tela. Para as
plataformas de deploy, `deploy/preparar_publicacao.py` separa o que cada uma precisa.

Uso:
    python deploy/gerar_segredos.py            # não sobrescreve um .env existente
    python deploy/gerar_segredos.py --forcar
"""

from __future__ import annotations

import hashlib
import json
import secrets
import sys
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

RAIZ = Path(__file__).resolve().parents[1]
IDENTIDADES = ["doador:D-0008", "doador:D-0211", "ong:O-023", "ong:O-005", "admin:A-01"]


def main() -> None:
    env = RAIZ / ".env"
    if env.exists() and "--forcar" not in sys.argv:
        sys.exit(".env já existe (use --forcar para gerar outro).")
    chave = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    pem = chave.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                              serialization.NoEncryption()).decode()
    (RAIZ / "segredos").mkdir(exist_ok=True)
    (RAIZ / "segredos" / "chave-publica-declaracao.pem").write_bytes(chave.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo))

    hashes, claras = {}, []
    for ident in IDENTIDADES:
        papel, id_ = ident.split(":")
        k = f"ra_{papel}_{secrets.token_urlsafe(24)}"
        hashes[hashlib.sha256(k.encode()).hexdigest()] = {"papel": papel, "id": id_}
        claras.append(f"{ident}\t{k}")
    (RAIZ / "segredos" / "chaves-api.txt").write_text("\n".join(claras) + "\n", encoding="utf-8")

    linhas = {
        "REDE_ALIMENTA_AMBIENTE": "producao",
        "REDE_ALIMENTA_CHAVE_HMAC": secrets.token_hex(32),
        "REDE_ALIMENTA_CHAVE_PSEUDONIMO": secrets.token_hex(32),
        "REDE_ALIMENTA_CHAVE_LOG": secrets.token_hex(32),
        "REDE_ALIMENTA_CHAVE_DECLARACAO_PEM": pem.replace("\n", "\\n"),  # uma linha; a API desfaz o \n
        "REDE_ALIMENTA_CHAVES_API": json.dumps(hashes, separators=(",", ":")),
        "REDE_ALIMENTA_DATABASE_URL": "",
        "REDE_ALIMENTA_DASHBOARD_DB_URL": "",
        "POSTGRES_SENHA_LOCAL": secrets.token_urlsafe(18),
    }
    env.write_text("".join(f"{k}={v}\n" for k, v in linhas.items()), encoding="utf-8")
    print("Gerados: .env, segredos/chaves-api.txt (chaves de API em claro), segredos/chave-publica-declaracao.pem")
    print("Nada disso vai para o Git. Preencha as URLs do banco no .env quando o Supabase estiver pronto.")


if __name__ == "__main__":
    main()

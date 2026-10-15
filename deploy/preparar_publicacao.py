"""Separa, a partir do .env, só os segredos que cada plataforma precisa (menor privilégio):

- segredos/render.env               → Render (API): "Environment" → "Add from .env"
- segredos/streamlit-secrets.toml   → Streamlit Community Cloud (dashboard): "Settings" → "Secrets"

O dashboard recebe SÓ a conexão de leitura (papel rede_dashboard); nenhuma chave da API.
Nada é impresso na tela; a pasta segredos/ não vai para o Git.

Uso:
    .venv\\Scripts\\python deploy\\preparar_publicacao.py https://rede-alimenta-api.onrender.com
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
API = ["REDE_ALIMENTA_AMBIENTE", "REDE_ALIMENTA_CHAVE_HMAC", "REDE_ALIMENTA_CHAVE_PSEUDONIMO", "REDE_ALIMENTA_CHAVE_LOG",
       "REDE_ALIMENTA_CHAVE_DECLARACAO_PEM", "REDE_ALIMENTA_CHAVES_API", "REDE_ALIMENTA_DATABASE_URL"]


def main() -> None:
    url_api = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "https://rede-alimenta-api.onrender.com"
    env = {}
    for linha in (RAIZ / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            env[k.strip()] = v.strip()
    faltando = [k for k in API + ["REDE_ALIMENTA_DASHBOARD_DB_URL"] if not env.get(k)]
    if faltando:
        sys.exit(f"Faltam no .env: {faltando}")

    destino = RAIZ / "segredos"
    destino.mkdir(exist_ok=True)
    (destino / "render.env").write_text("".join(f"{k}={env[k]}\n" for k in API), encoding="utf-8")
    toml = (f"REDE_ALIMENTA_DASHBOARD_DB_URL = {json.dumps(env['REDE_ALIMENTA_DASHBOARD_DB_URL'])}\n"
            f"REDE_ALIMENTA_API_PUBLICA = {json.dumps(url_api)}\n")
    (destino / "streamlit-secrets.toml").write_text(toml, encoding="utf-8")
    print("[OK] segredos/render.env (7 variáveis da API)")
    print("[OK] segredos/streamlit-secrets.toml (só a conexão de leitura do dashboard + URL da API)")


if __name__ == "__main__":
    main()

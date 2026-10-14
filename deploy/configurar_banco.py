"""Configura os papéis de menor privilégio no Supabase e preenche o .env, sem mostrar nenhuma senha.

1. Pede a URI de DONO do banco (a mesma da carga), sem eco na tela.
2. Gera senhas fortes para `rede_api` e `rede_dashboard` e aplica com ALTER ROLE.
3. Monta as URIs de cada papel e grava no .env (que não vai para o Git).
4. Testa: a API lê o cadastro; o dashboard lê as visões e NÃO lê as tabelas.

Uso:
    .venv\\Scripts\\python deploy\\configurar_banco.py
"""

from __future__ import annotations

import getpass
import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

import psycopg
from psycopg import sql

RAIZ = Path(__file__).resolve().parents[1]
ENV = RAIZ / ".env"


def uri_do_papel(uri_dono: str, papel: str, senha: str) -> str:
    p = urlsplit(uri_dono)
    usuario = p.username or ""
    # No pooler do Supabase o usuário é "<papel>.<código do projeto>".
    projeto = usuario.split(".", 1)[1] if "." in usuario else ""
    novo_usuario = f"{papel}.{projeto}" if projeto else papel
    netloc = f"{quote(novo_usuario)}:{quote(senha)}@{p.hostname}" + (f":{p.port}" if p.port else "")
    return urlunsplit((p.scheme, netloc, p.path, p.query, p.fragment))


def gravar_env(valores: dict[str, str]) -> None:
    texto = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    for chave, valor in valores.items():
        linha = f"{chave}={valor}"
        if re.search(rf"^{chave}=.*$", texto, flags=re.M):
            texto = re.sub(rf"^{chave}=.*$", lambda _: linha, texto, flags=re.M)
        else:
            texto += ("" if texto.endswith("\n") or not texto else "\n") + linha + "\n"
    ENV.write_text(texto, encoding="utf-8")


def main() -> None:
    import os

    # No Windows, o campo oculto do getpass não aceita colar: a variável de ambiente é o caminho padrão.
    uri_dono = os.environ.get("REDE_ALIMENTA_DB_ADMIN_URL", "").strip().strip('"')
    if not uri_dono:
        print("Cole a URI do Session pooler (a MESMA da carga) e tecle Enter. Nada aparece enquanto você cola.")
        uri_dono = getpass.getpass("URI: ").strip().strip('"')
    if not uri_dono.startswith("postgresql://"):
        sys.exit("Isso não parece uma URI do Supabase (deve começar com postgresql://). Nada foi alterado.")

    senhas = {papel: secrets.token_hex(20) for papel in ("rede_api", "rede_dashboard")}
    try:
        with psycopg.connect(uri_dono, autocommit=True, connect_timeout=10) as c:
            for papel, senha in senhas.items():
                c.execute(sql.SQL("ALTER ROLE {} WITH LOGIN PASSWORD {}").format(
                    sql.Identifier(papel), sql.Literal(senha)))
    except psycopg.Error as e:
        sys.exit(f"Não consegui conectar como dono do banco: {type(e).__name__}. Confira a URI e a senha.")
    print("[OK] senhas dos papéis rede_api e rede_dashboard definidas")

    uri_api = uri_do_papel(uri_dono, "rede_api", senhas["rede_api"])
    uri_dash = uri_do_papel(uri_dono, "rede_dashboard", senhas["rede_dashboard"])
    gravar_env({"REDE_ALIMENTA_DATABASE_URL": uri_api, "REDE_ALIMENTA_DASHBOARD_DB_URL": uri_dash})
    print("[OK] .env atualizado (REDE_ALIMENTA_DATABASE_URL e REDE_ALIMENTA_DASHBOARD_DB_URL)")

    try:
        with psycopg.connect(uri_api, connect_timeout=10) as c:
            n = c.execute("SELECT count(*) FROM rede.ongs").fetchone()[0]
        print(f"[OK] papel rede_api conecta e lê o cadastro ({n} ONGs)")
        with psycopg.connect(uri_dash, connect_timeout=10) as c:
            n = c.execute("SELECT count(*) FROM rede.vw_impacto_regiao").fetchone()[0]
            print(f"[OK] papel rede_dashboard conecta e lê as visões ({n} regiões)")
            try:
                c.execute("SELECT 1 FROM rede.doadores LIMIT 1")
                print("[ATENÇÃO] rede_dashboard conseguiu ler a tabela de doadores: não devia!")
            except psycopg.errors.InsufficientPrivilege:
                print("[OK] papel rede_dashboard NÃO lê as tabelas (menor privilégio funcionando)")
    except psycopg.Error as e:
        sys.exit(f"Teste de conexão dos papéis falhou: {type(e).__name__}: {str(e).splitlines()[0][:150]}")
    print("Pronto. As senhas estão só no .env (fora do Git).")


if __name__ == "__main__":
    main()

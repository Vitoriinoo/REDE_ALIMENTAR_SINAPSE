"""Cria as contas de demonstração do login real: uma por papel, ligada a um registro simulado existente.

- doador D-0008 (restaurante PJ), ONG O-005, transportador V-001 e admin A-01.
- Senhas fortes geradas aqui e gravadas só em `segredos/contas-demo.txt` (fora do Git). Nada de
  senha, e-mail em claro de banco ou chave aparece na tela.
- Usa as chaves do `.env` (a mesma `REDE_ALIMENTA_CHAVE_HMAC` da API; senão o e-mail não bate no login).
- Com `REDE_ALIMENTA_DATABASE_URL`, grava em `rede.contas` no Supabase (precisa da migração
  `db/migracoes/2026-10-15_contas.sql` aplicada). Com `--local`, grava em `var/contas.json` (API sem banco).
- Idempotente: conta que já existe é mantida (com a senha que já está no arquivo).

Uso:
    .venv\\Scripts\\python deploy\\criar_contas_demo.py [--local]
"""

from __future__ import annotations

import os
import secrets
import sys
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

DESTINO = RAIZ / "segredos" / "contas-demo.txt"
DEMO = [  # (papel, código do registro existente, nome exibido, e-mail)
    ("doador", "D-0008", "Restaurante demonstração", "doador.demo@redealimenta.org"),
    ("ong", "O-005", "ONG demonstração", "ong.demo@redealimenta.org"),
    ("transportador", "V-001", "Transportador demonstração", "transportador.demo@redealimenta.org"),
    ("admin", "A-01", "Administração da plataforma", "admin.demo@redealimenta.org"),
]


def carregar_env() -> None:
    """Lê o .env sem sobrescrever o que já está no ambiente e sem mostrar nada."""
    arquivo = RAIZ / ".env"
    if not arquivo.exists():
        return
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"'))


def _senhas_existentes() -> dict[str, str]:
    if not DESTINO.exists():
        return {}
    return dict(l.split("\t")[1:3] for l in DESTINO.read_text(encoding="utf-8").splitlines() if l.count("\t") == 2)


def _documento_hash(papel: str, codigo: str) -> str:
    import pandas as pd

    from src.seguranca.senhas import hmac_documento

    tabela = {"doador": ("doadores.csv", "doador_id"), "ong": ("ongs.csv", "ong_id")}.get(papel)
    if tabela:
        df = pd.read_csv(RAIZ / "data" / "processed" / tabela[0])
        linha = df.loc[df[tabela[1]] == codigo]
        if len(linha):
            return str(linha.iloc[0]["documento_hash"])
    return hmac_documento(f"DEMO{codigo}")  # transportador e admin simulados não têm documento


def _tipo_doador(codigo: str) -> str:
    import pandas as pd

    df = pd.read_csv(RAIZ / "data" / "processed" / "doadores.csv")
    return str(df.loc[df["doador_id"] == codigo].iloc[0]["tipo_doador"])


def criar(repo) -> list[tuple[str, str, str]]:
    from src.seguranca import senhas

    existentes = _senhas_existentes()
    linhas = []
    for papel, codigo, nome, email in DEMO:
        senha = existentes.get(email)
        if repo.por_email_hash(senhas.hmac_email(email)) is None:
            senha = secrets.token_urlsafe(18)
            repo.inserir({
                "codigo": codigo, "email_hash": senhas.hmac_email(email), "senha_hash": senhas.gerar_hash(senha),
                "papel": papel, "nome": nome, "documento_hash": _documento_hash(papel, codigo),
                "tipo_doador": _tipo_doador(codigo) if papel == "doador" else None,
                "veiculo": "carro" if papel == "transportador" else None,  # V-001 é carro no dataset
                "status": "ativa", "criado_em": datetime.now(timezone.utc),
            })
            print(f"criada: {papel} {codigo}")
        else:
            print(f"já existia: {papel} {codigo}")
        linhas.append((f"{papel}:{codigo}", email, senha or "(senha anterior não encontrada no arquivo)"))
    return linhas


def main(local: bool) -> None:
    carregar_env()
    from src.api.contas import RepositorioContasMemoria, RepositorioContasPostgres

    url = os.environ.get("REDE_ALIMENTA_DATABASE_URL")
    if url and not local:
        repo, onde = RepositorioContasPostgres(url), "Supabase (rede.contas)"
    else:
        dir_var = Path(os.environ.get("REDE_ALIMENTA_DIR_VAR", RAIZ / "var"))
        repo, onde = RepositorioContasMemoria(dir_var / "contas.json"), "var/contas.json (API local sem banco)"
    linhas = criar(repo)
    DESTINO.parent.mkdir(exist_ok=True)
    DESTINO.write_text("".join(f"{a}\t{b}\t{c}\n" for a, b, c in linhas), encoding="utf-8")
    print(f"Contas em {onde}. E-mails e senhas em {DESTINO.relative_to(RAIZ)} (NÃO versionar).")


if __name__ == "__main__":
    main(local="--local" in sys.argv[1:])

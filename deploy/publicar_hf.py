"""Publica a API e o dashboard em dois Hugging Face Spaces (Docker). Chamado pelo GitHub Actions
depois do security gate; também pode rodar à mão:  HF_TOKEN=... HF_USUARIO=... python deploy/publicar_hf.py

Cada Space recebe só o que a imagem dele precisa (menor superfície). Os segredos NÃO vão no
upload: ficam nas "Secrets" de cada Space (ver README §Deploy).
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

from huggingface_hub import HfApi

RAIZ = Path(__file__).resolve().parents[1]

CABECALHO = """---
title: {titulo}
emoji: 🥫
colorFrom: green
colorTo: blue
sdk: docker
app_port: {porta}
pinned: false
license: mit
short_description: {descricao}
---

# {titulo}

Parte do projeto **Rede Alimenta IA** (FIAP, Projeto Integrador IA + DevSecOps).
Código-fonte, testes, pipeline e documentação: https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE

Este Space é publicado automaticamente pelo GitHub Actions, só depois de o security gate
(Bandit + Trivy + testes) aprovar.
"""

SPACES = {
    "api": {
        "nome": "rede-alimenta-api", "titulo": "Rede Alimenta IA - API", "porta": 7860, "alvo": "completo",
        "descricao": "API FastAPI (Swagger em /docs) com IA de prioridade e descarte",
        "arquivos": ["src", "data/processed", "db", "requirements/base.txt", "requirements/api.txt",
                     "requirements/ia.txt", ".dockerignore"],
    },
    "dashboard": {
        "nome": "rede-alimenta-dashboard", "titulo": "Rede Alimenta IA - Dashboard", "porta": 8501,
        "alvo": "dashboard", "descricao": "Impacto social, qualidade da IA e indicadores de segurança",
        "arquivos": ["src", "data/processed/lotes.csv", "data/processed/doadores.csv", "data/processed/ongs.csv",
                     "data/reference/regioes.csv", "reports", ".streamlit", "requirements/base.txt",
                     "requirements/dashboard.txt", ".dockerignore"],
    },
}


def montar(cfg: dict, destino: Path) -> None:
    for item in cfg["arquivos"]:
        origem = RAIZ / item
        alvo = destino / item
        alvo.parent.mkdir(parents=True, exist_ok=True)
        if origem.is_dir():
            shutil.copytree(origem, alvo, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_*.log"))
        else:
            shutil.copy2(origem, alvo)
    dockerfile = (RAIZ / "Dockerfile").read_text(encoding="utf-8")
    # O Space constrói o ÚLTIMO estágio: anexa um estágio final que aponta para o alvo certo.
    (destino / "Dockerfile").write_text(dockerfile + f"\nFROM {cfg['alvo']} AS final\n", encoding="utf-8")
    (destino / "README.md").write_text(CABECALHO.format(**cfg), encoding="utf-8")


def main() -> None:
    api = HfApi(token=os.environ["HF_TOKEN"])
    usuario = os.environ["HF_USUARIO"]
    for cfg in SPACES.values():
        repo = f"{usuario}/{cfg['nome']}"
        api.create_repo(repo, repo_type="space", space_sdk="docker", exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            montar(cfg, Path(tmp))
            api.upload_folder(folder_path=tmp, repo_id=repo, repo_type="space", delete_patterns="*",
                              commit_message=f"deploy {os.environ.get('GITHUB_SHA', 'manual')[:7]}")
        print(f"publicado: https://huggingface.co/spaces/{repo}")


if __name__ == "__main__":
    main()

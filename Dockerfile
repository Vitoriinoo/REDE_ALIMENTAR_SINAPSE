# syntax=docker/dockerfile:1.7
# =============================================================================================
# Rede Alimenta IA: uma imagem por responsabilidade (menor privilégio, SDD §8)
#   api         FastAPI, sem torch e sem modelos: decide com as regras e chama a inferência
#   inferencia  só os modelos (M1, M2, NLP); sem segredos; no Compose, rede interna sem saída
#   dashboard   Streamlit, só lê visões agregadas
#   completo    API + modelos no mesmo processo (Hugging Face Space da API, que é um container só)
# Build:  docker build --target api -t rede-alimenta/api .     (ou: docker compose build)
# =============================================================================================
ARG PYTHON=python:3.12-slim-bookworm

FROM ${PYTHON} AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore
# Atualiza os pacotes do SO (correções de CVE que o Trivy cobra) e cria o usuário sem privilégios
# (UID 1000: o Hugging Face Spaces roda o container com esse UID).
RUN apt-get update && apt-get upgrade -y --no-install-recommends && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /usr/sbin/nologin app
WORKDIR /app
# pip atualizado ANTES de instalar qualquer coisa (Trivy: 6 CVEs no pip 25.0.1 da imagem base, ex.
# CVE-2026-13346 instalação arbitrária via índice malicioso). No fim de cada alvo o pip é REMOVIDO:
# em produção ninguém instala pacote, e o que não existe não pode ser explorado.
RUN python -m pip install --upgrade pip==26.2.0
COPY requirements/base.txt requirements/base.txt

# --- inferência ----------------------------------------------------------------------------
FROM base AS inferencia-build
COPY requirements/ia.txt requirements/ia.txt
# torch CPU vem do índice oficial do PyTorch (a roda do PyPI traz CUDA: +2 GB sem uso).
RUN pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements/ia.txt
# O índice do PyTorch traz setuptools 78.1.0 (Trivy: CVE-2025-47273 path traversal, e wheel/jaraco
# vendorizados com CVE ALTO): atualiza para a versão corrigida, vinda do PyPI.
RUN pip install --upgrade setuptools==83.0.0
COPY src/ src/
COPY data/processed/lotes.csv data/processed/lotes.csv
ENV HF_HOME=/app/hf
# Modelos construídos NO BUILD a partir do dataset versionado: o SHA-256 de cada artefato fica nos
# metadados e é conferido antes do joblib.load. O modelo HF é baixado aqui, fixado por commit, e o
# container roda OFFLINE (sem rede de saída).
RUN mkdir -p models reports \
    && python -m src.models.treinar > /dev/null \
    && python -c "from src.models.nlp import ClassificadorSimilaridade as C; C()"
ENV HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1

FROM inferencia-build AS inferencia
RUN python -m pip uninstall -y pip
USER app
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8001/saude', timeout=4)"
CMD ["uvicorn", "src.inferencia.servico:app", "--host", "0.0.0.0", "--port", "8001", "--no-server-header"]

# --- API -----------------------------------------------------------------------------------
FROM base AS api
COPY requirements/api.txt requirements/api.txt
RUN pip install -r requirements/api.txt && python -m pip uninstall -y pip
COPY src/ src/
COPY data/processed/ data/processed/
COPY db/ db/
RUN mkdir -p var && chown app:app var
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=4)"
CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--no-server-header", "--proxy-headers"]

# --- dashboard -----------------------------------------------------------------------------
FROM base AS dashboard
COPY requirements/dashboard.txt requirements/dashboard.txt
RUN pip install -r requirements/dashboard.txt && python -m pip uninstall -y pip
COPY src/ src/
COPY data/processed/lotes.csv data/processed/doadores.csv data/processed/ongs.csv data/processed/
COPY data/reference/regioes.csv data/reference/regioes.csv
COPY reports/ reports/
COPY .streamlit/ .streamlit/
USER app
ENV PORT=8501
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD python -c "import os, urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ[\"PORT\"]}/_stcore/health', timeout=4)"
CMD ["sh", "-c", "streamlit run src/dashboard/app.py --server.port ${PORT} --server.address 0.0.0.0"]

# --- completo (HF Space da API: um container só, porta 7860) -------------------------------
FROM inferencia-build AS completo
COPY requirements/api.txt requirements/api.txt
RUN pip install -r requirements/api.txt && python -m pip uninstall -y pip
COPY data/processed/ data/processed/
COPY db/ db/
RUN mkdir -p var && chown app:app var
USER app
ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "uvicorn src.api.app:app --host 0.0.0.0 --port ${PORT} --no-server-header --proxy-headers"]

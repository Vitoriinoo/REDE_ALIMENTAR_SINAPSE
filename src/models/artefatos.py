"""Carregamento seguro dos modelos treinados.

Um .joblib é um pickle: desserializar um arquivo adulterado pode executar código
arbitrário. Por isso o modelo só é carregado se o SHA-256 do arquivo bater com o
registrado nos metadados no momento do treino (src/models/treinar.py).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import joblib

from src.models.treinar import DIR_MODELOS


class ArtefatoAdulterado(RuntimeError):
    pass


def carregar_modelo(nome: str, diretorio: Path = DIR_MODELOS):
    """Devolve (pipeline, metadados) após validar a integridade do artefato."""
    metadados = json.loads((diretorio / f"{nome}.json").read_text(encoding="utf-8"))
    caminho = diretorio / metadados["artefato"]
    sha = hashlib.sha256(caminho.read_bytes()).hexdigest()
    if sha != metadados["sha256_artefato"]:
        raise ArtefatoAdulterado(f"SHA-256 de {caminho.name} não confere com os metadados: não carregar.")
    return joblib.load(caminho), metadados  # nosec B301 - integridade verificada acima

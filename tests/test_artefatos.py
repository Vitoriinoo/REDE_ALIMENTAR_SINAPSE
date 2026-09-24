"""Integridade dos artefatos de modelo (STRIDE: adulteração do .joblib / supply chain)."""

import hashlib
import json

import joblib
import pytest

from src.models.artefatos import ArtefatoAdulterado, carregar_modelo


def _salvar(diretorio, objeto):
    caminho = diretorio / "modelo_teste.joblib"
    joblib.dump(objeto, caminho)
    meta = {"artefato": caminho.name, "sha256_artefato": hashlib.sha256(caminho.read_bytes()).hexdigest()}
    (diretorio / "modelo_teste.json").write_text(json.dumps(meta), encoding="utf-8")
    return caminho


def test_carrega_artefato_integro(tmp_path):
    _salvar(tmp_path, {"pesos": [1, 2, 3]})
    modelo, meta = carregar_modelo("modelo_teste", tmp_path)
    assert modelo == {"pesos": [1, 2, 3]}


def test_recusa_artefato_adulterado(tmp_path):
    caminho = _salvar(tmp_path, {"pesos": [1, 2, 3]})
    joblib.dump({"pesos": "adulterado"}, caminho)  # troca o arquivo sem atualizar o hash
    with pytest.raises(ArtefatoAdulterado):
        carregar_modelo("modelo_teste", tmp_path)

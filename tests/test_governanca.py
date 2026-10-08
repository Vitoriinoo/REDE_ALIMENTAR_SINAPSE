"""Governança de dados verificada por teste (regras 11): coluna sem classificação quebra o pipeline."""

import pandas as pd
import pytest

from src.data.curadoria_ipvs import RAIZ
from src.governanca.catalogo import CATALOGO, Classe
from src.governanca.qualidade import checar


@pytest.mark.parametrize("arquivo", sorted(CATALOGO))
def test_toda_coluna_do_dataset_esta_classificada(arquivo):
    colunas = set(pd.read_csv(RAIZ / arquivo, nrows=0).columns)
    sem_classificacao = colunas - set(CATALOGO[arquivo])
    assert not sem_classificacao, f"Classifique em src/governanca/catalogo.py: {sorted(sem_classificacao)}"
    sobrando = set(CATALOGO[arquivo]) - colunas
    assert not sobrando, f"Catálogo descreve colunas que não existem mais: {sorted(sobrando)}"


def test_todo_arquivo_de_dados_esta_no_catalogo():
    arquivos = {str(p.relative_to(RAIZ)).replace("\\", "/") for pasta in ("data/processed", "data/reference")
                for p in (RAIZ / pasta).glob("*.csv*")}
    assert arquivos == set(CATALOGO)


def test_texto_livre_tem_retencao_curta():
    textos = [c for cols in CATALOGO.values() for c in cols.values() if c.classe == Classe.TEXTO_LIVRE]
    assert textos and all(c.retencao == "90 dias" for c in textos)


def test_qualidade_dos_dados_gerados():
    falhas = [c for c in checar() if not c["ok"]]
    assert not falhas, falhas

"""Contas de demonstração: uma por papel, ligadas a registros existentes, senha só no arquivo de segredos."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from src.api.contas import Contas, RepositorioContasMemoria

_spec = importlib.util.spec_from_file_location(
    "criar_contas_demo", Path(__file__).resolve().parents[1] / "deploy" / "criar_contas_demo.py")
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)


def test_uma_conta_por_papel_que_entra_e_senha_nunca_na_tela(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(demo, "DESTINO", tmp_path / "contas-demo.txt")
    repo = RepositorioContasMemoria(tmp_path / "contas.json")
    linhas = demo.criar(repo)
    demo.DESTINO.write_text("".join(f"{a}\t{b}\t{c}\n" for a, b, c in linhas), encoding="utf-8")

    saida = capsys.readouterr().out
    contas = Contas(repo)
    for ident, email, senha in linhas:
        assert senha not in saida
        conta = contas.entrar(email, senha)
        assert f"{conta['papel']}:{conta['codigo']}" == ident
    assert {l[0] for l in linhas} == {"doador:D-0008", "ong:O-005", "transportador:V-001", "admin:A-01"}
    assert contas.por_codigo("D-0008")["tipo_doador"] == "PJ"


def test_rodar_de_novo_mantem_as_contas_e_as_senhas(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "DESTINO", tmp_path / "contas-demo.txt")
    repo = RepositorioContasMemoria(tmp_path / "contas.json")
    primeira = demo.criar(repo)
    demo.DESTINO.write_text("".join(f"{a}\t{b}\t{c}\n" for a, b, c in primeira), encoding="utf-8")
    segunda = demo.criar(RepositorioContasMemoria(tmp_path / "contas.json"))  # relê do arquivo
    assert primeira == segunda

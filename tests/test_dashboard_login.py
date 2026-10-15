"""Tela de entrada: login por e-mail e senha, cadastro por papel e navegação conforme o papel da conta."""

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.dashboard import cliente_api
from src.dashboard.paginas import login

CPF = "52998224725"
CNPJ = "11222333000181"
RAIZ = Path(__file__).resolve().parents[1]
LOGIN = str(RAIZ / "src/dashboard/paginas/login.py")
APP = str(RAIZ / "src/dashboard/app.py")


def _corpo(papel, documento, **extra):
    return login.montar_cadastro(papel, "Fulano", " Fulano@Exemplo.org ", documento, "senha-forte-123", **extra)


def test_documento_por_papel():
    assert login.documento_esperado("ong") == "CNPJ"
    assert login.documento_esperado("transportador") == "CPF"
    assert login.documento_esperado("doador", "PF") == "CPF"
    assert login.documento_esperado("doador", "PJ") == "CNPJ"


def test_corpo_so_com_campos_do_papel():
    d = _corpo("doador", CPF, tipo_doador="PF", veiculo="moto")
    assert d["tipo_doador"] == "PF" and "veiculo" not in d and d["email"] == "fulano@exemplo.org"
    t = _corpo("transportador", CPF, veiculo="carro")
    assert t["veiculo"] == "carro" and "tipo_doador" not in t
    o = _corpo("ong", CNPJ)
    assert "tipo_doador" not in o and "veiculo" not in o


@pytest.mark.parametrize("corpo", [
    _corpo("doador", CPF, tipo_doador="PF"),
    _corpo("doador", CNPJ, tipo_doador="PJ"),
    _corpo("ong", CNPJ),
    _corpo("transportador", CPF, veiculo="utilitario"),
])
def test_cadastros_validos_passam(corpo):
    assert login.problemas_cadastro(corpo, "senha-forte-123") == []


def test_cadastro_recusa_documento_errado_senha_curta_e_admin():
    assert any("CNPJ" in e for e in login.problemas_cadastro(_corpo("ong", CPF), "senha-forte-123"))
    assert any("CPF" in e for e in login.problemas_cadastro(_corpo("doador", CNPJ, tipo_doador="PF"), "senha-forte-123"))
    assert any("CPF" in e for e in login.problemas_cadastro(_corpo("transportador", "11111111111", veiculo="moto"), "senha-forte-123"))
    curta = login.montar_cadastro("ong", "X", "a@b.org", CNPJ, "curta")
    assert any("10" in e for e in login.problemas_cadastro(curta, "curta"))
    assert any("conferem" in e for e in login.problemas_cadastro(_corpo("ong", CNPJ), "outra-senha-123"))
    assert login.problemas_cadastro(_corpo("admin", CPF), "senha-forte-123")  # admin não se cadastra
    assert login.problemas_cadastro(_corpo("transportador", CPF, veiculo="van"), "senha-forte-123")


def test_login_guarda_so_identidade_e_token(monkeypatch):
    monkeypatch.setattr(cliente_api, "entrar", lambda e, s: {"token": "ras_x", "papel": "ong", "id": "O-001",
                                                             "nome": "ONG Teste", "expira_em": "..."}, raising=False)
    estado = {}
    assert login.entrar("o@x.org", "senha-forte-123", estado) is None
    assert estado == {"ident": {"papel": "ong", "id": "O-001", "nome": "ONG Teste"}, "chave": "ras_x"}
    assert "senha-forte-123" not in str(estado)


@pytest.mark.parametrize("status,trecho", [(401, "inválidos"), (429, "tentativas"), (403, "não liberada"), (0, "indispon")])
def test_login_erros_amigaveis(monkeypatch, status, trecho):
    def falha(e, s):
        raise cliente_api.ErroAPI(status, "API indisponível" if status == 0 else "motivo")
    monkeypatch.setattr(cliente_api, "entrar", falha, raising=False)
    estado = {}
    assert trecho in login.entrar("o@x.org", "senha-forte-123", estado)
    assert estado == {}


def test_tela_entrar_conecta(monkeypatch):
    monkeypatch.setattr(cliente_api, "entrar", lambda e, s: {"token": "ras_t", "papel": "transportador",
                                                             "id": "V-001", "nome": "Tito"}, raising=False)
    at = AppTest.from_file(LOGIN).run()
    assert not at.exception
    at.text_input[0].input("t@x.org")
    at.text_input[1].input("senha-forte-123")
    at.button[0].click().run()
    assert at.session_state["ident"] == {"papel": "transportador", "id": "V-001", "nome": "Tito"}
    assert at.session_state["chave"] == "ras_t"


def test_tela_cadastro_ong_pendente_nao_entra(monkeypatch):
    enviados = []
    monkeypatch.setattr(cliente_api, "cadastrar",
                        lambda d: enviados.append(d) or {"id": "O-9", "papel": "ong", "status": "pendente"}, raising=False)
    at = AppTest.from_file(LOGIN).run()
    at.radio(key="cad_papel").set_value("ong").run()
    campos = [t for t in at.text_input if t.label in ("Nome da instituição", "E-mail", "CNPJ", "Senha", "Repita a senha")]
    nomes = {}
    for t in campos:
        nomes.setdefault(t.label, []).append(t)
    nomes["Nome da instituição"][0].input("ONG Teste")
    nomes["E-mail"][-1].input("ong@x.org")  # o primeiro "E-mail" é o da aba Entrar
    nomes["CNPJ"][0].input(CNPJ)
    nomes["Senha"][-1].input("senha-forte-123")
    nomes["Repita a senha"][0].input("senha-forte-123")
    next(b for b in at.button if b.label == "Criar conta").click().run()
    assert not at.exception
    assert enviados and enviados[0]["papel"] == "ong" and enviados[0]["documento"] == CNPJ
    assert "ident" not in at.session_state
    assert any("pendente" in w.value for w in at.warning)


@pytest.mark.parametrize("papel,paginas", [
    (None, {"login", "painel"}),
    ("doador", {"doador", "documentos", "painel"}),
    ("ong", {"ong", "painel"}),
    ("transportador", {"transportador", "painel"}),
    ("admin", {"admin", "documentos", "painel"}),
])
def test_navegacao_por_papel(monkeypatch, papel, paginas):
    vistos = []
    import streamlit as st
    monkeypatch.setattr(st, "navigation", lambda ps: vistos.extend(ps) or type("N", (), {"run": lambda self: None})())
    at = AppTest.from_file(APP)
    if papel:
        at.session_state["ident"] = {"papel": papel, "id": "X-1", "nome": "Teste"}
        at.session_state["chave"] = "ras_t"
    at.run()
    assert not at.exception
    assert {Path(str(p._page)).stem for p in vistos} == paginas
    padrao = [Path(str(p._page)).stem for p in vistos if p._default]
    assert padrao == [next(iter(paginas - {"painel", "documentos"}))]

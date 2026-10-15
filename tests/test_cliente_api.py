"""Cliente da API usado pelas telas: Bearer para token de sessão, entrar() e cadastrar()."""

from __future__ import annotations

import httpx
import pytest

from src.dashboard import cliente_api


class _Gravador:
    def __init__(self, status=200, corpo=None):
        self.status, self.corpo, self.chamadas = status, corpo or {}, []

    def __call__(self, metodo, url, headers=None, json=None, timeout=None):
        self.chamadas.append({"metodo": metodo, "url": url, "headers": headers or {}, "json": json})
        return httpx.Response(self.status, json=self.corpo, request=httpx.Request(metodo, url))


def test_token_de_sessao_vai_como_bearer(monkeypatch):
    g = _Gravador(corpo={"papel": "ong"})
    monkeypatch.setattr(cliente_api.httpx, "request", g)
    cliente_api.chamar("GET", "/v1/eu", "ras_abc.def")
    assert g.chamadas[0]["headers"] == {"Authorization": "Bearer ras_abc.def"}


def test_chave_de_api_continua_no_cabecalho_antigo(monkeypatch):
    g = _Gravador()
    monkeypatch.setattr(cliente_api.httpx, "request", g)
    cliente_api.chamar("GET", "/v1/eu", "ra_doador_xyz")
    assert g.chamadas[0]["headers"] == {"X-Chave-API": "ra_doador_xyz"}


def test_entrar_manda_email_e_senha_e_devolve_a_sessao(monkeypatch):
    g = _Gravador(corpo={"token": "ras_x.y", "papel": "doador", "id": "D-0008", "nome": "P", "expira_em": "z"})
    monkeypatch.setattr(cliente_api.httpx, "request", g)
    assert cliente_api.entrar("a@b.com", "senha-longa-123")["token"] == "ras_x.y"
    assert g.chamadas[0]["metodo"] == "POST" and g.chamadas[0]["url"].endswith("/v1/auth/login")
    assert g.chamadas[0]["json"] == {"email": "a@b.com", "senha": "senha-longa-123"}
    assert "Authorization" not in g.chamadas[0]["headers"]


def test_cadastrar_repassa_os_dados_e_levanta_erro_da_api(monkeypatch):
    g = _Gravador(status=422, corpo={"detail": "e-mail já cadastrado"})
    monkeypatch.setattr(cliente_api.httpx, "request", g)
    with pytest.raises(cliente_api.ErroAPI) as e:
        cliente_api.cadastrar({"papel": "ong", "email": "a@b.com"})
    assert e.value.status == 422 and e.value.mensagem == "e-mail já cadastrado"
    assert g.chamadas[0]["url"].endswith("/v1/auth/cadastro")

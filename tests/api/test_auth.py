"""Login real: cadastro por papel, login com e-mail e senha, token `ras_` e bloqueio após 5 falhas.

A Receita é simulada (sem rede). ONG só entra com CNPJ válido E ativo na Receita; Receita fora do
ar deixa a conta PENDENTE, nunca aprovada sem verificar.
"""

from __future__ import annotations

import itertools

import pytest
from fastapi.testclient import TestClient

from src.validacao.documentos import dv_cnpj
from src.validacao.receita import ConsultaSimulada

CNPJ_ONG = "11222333000181"
CNPJ_EMPRESA = "11444777000161"
CPF = "52998224725"
RECEITA = {
    CNPJ_ONG: {"cnpj": CNPJ_ONG, "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA",
               "codigo_natureza_juridica": 3999, "cnae_fiscal": 8800600},
    CNPJ_EMPRESA: {"cnpj": CNPJ_EMPRESA, "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA",
                   "codigo_natureza_juridica": 2062, "cnae_fiscal": 5611201},
}
SENHA = "senha-bem-longa-1"
_seq = itertools.count(1)


def _cnpj_novo(receita: dict | None = None) -> str:
    """CNPJ com dígito válido e diferente a cada chamada (uma conta por documento e papel).

    Por padrão já fica ATIVO na Receita simulada como restaurante (CNAE de alimentação)."""
    base = f"{next(_seq):08d}0001"
    cnpj = base + dv_cnpj(base)
    RECEITA[cnpj] = {"cnpj": cnpj, "situacao_cadastral": 2, "descricao_situacao_cadastral": "ATIVA",
                     "codigo_natureza_juridica": 2062, "cnae_fiscal": 5611201} | (receita or {})
    return cnpj


def _cnpj_fora_da_receita() -> str:
    base = f"{next(_seq):08d}0001"
    return base + dv_cnpj(base)


@pytest.fixture(scope="module")
def api(tmp_path_factory):
    mp = pytest.MonkeyPatch()
    mp.setenv("REDE_ALIMENTA_CARREGAR_MODELOS", "0")
    mp.delenv("REDE_ALIMENTA_INFERENCIA_URL", raising=False)
    mp.delenv("REDE_ALIMENTA_DATABASE_URL", raising=False)
    mp.delenv("REDE_ALIMENTA_AMBIENTE", raising=False)
    from src.api import app as modulo

    mp.setattr(modulo, "DIR_VAR", tmp_path_factory.mktemp("var"))
    with TestClient(modulo.app) as c:
        modulo.E.receita = ConsultaSimulada(RECEITA)
        yield c, modulo
    mp.undo()


def _cadastro(**campos) -> dict:
    return {"papel": "doador", "email": "padaria@exemplo.com", "senha": SENHA, "nome": "Padaria Sol",
            "documento": _cnpj_novo(), "tipo_doador": "PJ"} | campos


def _entrar(c, email, senha=SENHA):
    return c.post("/v1/auth/login", json={"email": email, "senha": senha})


def test_doador_cadastra_entra_e_usa_o_token_como_bearer(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json=_cadastro())
    assert r.status_code == 201, r.text
    assert r.json()["papel"] == "doador" and r.json()["status"] == "ativa"
    login = _entrar(c, "PADARIA@exemplo.com ")
    assert login.status_code == 200, login.text
    corpo = login.json()
    assert corpo["token"].startswith("ras_") and corpo["papel"] == "doador" and corpo["nome"] == "Padaria Sol"
    assert {"id", "expira_em"} <= set(corpo)
    eu = c.get("/v1/eu", headers={"Authorization": f"Bearer {corpo['token']}"})
    assert eu.status_code == 200 and eu.json()["id"] == corpo["id"]


def test_token_tambem_vale_no_cabecalho_x_chave_api(api):
    c, _ = api
    c.post("/v1/auth/cadastro", json=_cadastro(email="mercado@exemplo.com"))
    token = _entrar(c, "mercado@exemplo.com").json()["token"]
    assert c.get("/v1/eu", headers={"X-Chave-API": token}).status_code == 200


def test_chave_de_api_antiga_continua_valendo(api):
    c, _ = api
    assert c.get("/v1/eu", headers={"X-Chave-API": "dev:admin:A-01"}).json() == {"papel": "admin", "id": "A-01"}


def test_resposta_nunca_devolve_senha_documento_ou_hash(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="seguro@exemplo.com", documento=CNPJ_EMPRESA))
    texto = r.text + _entrar(c, "seguro@exemplo.com").text
    assert r.status_code == 201
    assert SENHA not in texto and CNPJ_EMPRESA not in texto and "scrypt" not in texto


def test_documento_guardado_so_como_hmac(api):
    c, modulo = api
    doc = _cnpj_novo()
    assert c.post("/v1/auth/cadastro", json=_cadastro(email="hmac@exemplo.com", documento=doc)).status_code == 201
    conta = modulo.E.contas.por_email("hmac@exemplo.com")
    assert doc not in str(conta) and "hmac@exemplo.com" not in str(conta)
    assert len(conta["documento_hash"]) == 64


def test_email_em_uso_e_senha_curta_sao_recusados(api):
    c, _ = api
    c.post("/v1/auth/cadastro", json=_cadastro(email="repetido@exemplo.com"))
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="repetido@exemplo.com"))
    assert r.status_code == 422 and "e-mail" in r.json()["detail"]
    assert c.post("/v1/auth/cadastro", json=_cadastro(email="curta@exemplo.com", senha="123456789")).status_code == 422


def test_documento_com_digito_errado_e_recusado(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="dv@exemplo.com", documento="11444777000162"))
    assert r.status_code == 422 and "CNPJ" in r.json()["detail"]
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="pf@exemplo.com", tipo_doador="PF", documento="52998224724"))
    assert r.status_code == 422 and "CPF" in r.json()["detail"]


def test_doador_pf_usa_cpf(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="pessoa@exemplo.com", tipo_doador="PF", documento=CPF))
    assert r.status_code == 201, r.text


def test_ong_com_cnpj_ativo_fica_ativa(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json={"papel": "ong", "email": "ong@exemplo.com", "senha": SENHA,
                                          "nome": "Casa Esperança", "documento": "11.222.333/0001-81"})
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "ativa"
    assert _entrar(c, "ong@exemplo.com").json()["papel"] == "ong"


def test_ong_com_cnpj_de_empresa_ou_inexistente_e_recusada(api):
    c, _ = api
    corpo = {"papel": "ong", "email": "empresa@exemplo.com", "senha": SENHA, "nome": "Empresa"}
    assert c.post("/v1/auth/cadastro", json=corpo | {"documento": CNPJ_EMPRESA}).status_code == 422
    assert c.post("/v1/auth/cadastro", json=corpo | {"documento": _cnpj_fora_da_receita()}).status_code == 422
    assert c.post("/v1/auth/cadastro", json=corpo | {"documento": CPF}).status_code == 422


def test_ong_com_receita_fora_do_ar_fica_pendente_e_nao_entra(api):
    c, modulo = api
    original = modulo.E.receita
    modulo.E.receita = ConsultaSimulada({}, indisponivel=True)
    try:
        r = c.post("/v1/auth/cadastro", json={"papel": "ong", "email": "pendente@exemplo.com", "senha": SENHA,
                                              "nome": "ONG Pendente", "documento": _cnpj_fora_da_receita()})
    finally:
        modulo.E.receita = original
    assert r.status_code == 201 and r.json()["status"] == "pendente"
    login = _entrar(c, "pendente@exemplo.com")
    assert login.status_code == 403 and "pendente" in login.json()["detail"]


def test_transportador_cadastra_com_cpf_e_veiculo(api):
    c, _ = api
    corpo = {"papel": "transportador", "email": "moto@exemplo.com", "senha": SENHA, "nome": "João",
             "documento": CPF, "veiculo": "moto"}
    assert c.post("/v1/auth/cadastro", json=corpo).status_code == 201
    repetido = c.post("/v1/auth/cadastro", json=corpo | {"email": "moto2@exemplo.com"})
    assert repetido.status_code == 422 and "documento" in repetido.json()["detail"]
    token = _entrar(c, "moto@exemplo.com").json()["token"]
    assert c.get("/v1/eu", headers={"Authorization": f"Bearer {token}"}).json()["papel"] == "transportador"
    assert c.post("/v1/auth/cadastro", json=corpo | {"email": "x@exemplo.com", "veiculo": "aviao"}).status_code == 422


def test_admin_nao_tem_cadastro_aberto(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json={"papel": "admin", "email": "adm@exemplo.com", "senha": SENHA,
                                          "nome": "Adm", "documento": CPF})
    assert r.status_code == 422


def test_papel_vem_da_conta_nao_do_corpo_do_login(api):
    c, _ = api
    c.post("/v1/auth/cadastro", json=_cadastro(email="papel@exemplo.com"))
    r = c.post("/v1/auth/login", json={"email": "papel@exemplo.com", "senha": SENHA, "papel": "admin"})
    assert r.status_code == 422  # campo extra é recusado (extra=forbid)


def test_erro_de_login_e_generico(api):
    c, _ = api
    c.post("/v1/auth/cadastro", json=_cadastro(email="generico@exemplo.com"))
    senha_errada = _entrar(c, "generico@exemplo.com", "senha-errada-123")
    inexistente = _entrar(c, "ninguem@exemplo.com")
    assert senha_errada.status_code == inexistente.status_code == 401
    assert senha_errada.json()["detail"] == inexistente.json()["detail"] == "e-mail ou senha inválidos"


def test_cinco_falhas_bloqueiam_ate_a_senha_certa(api):
    c, _ = api
    c.post("/v1/auth/cadastro", json=_cadastro(email="alvo@exemplo.com"))
    for _ in range(5):
        assert _entrar(c, "alvo@exemplo.com", "chute-errado-000").status_code == 401
    assert _entrar(c, "alvo@exemplo.com").status_code == 429


def test_token_adulterado_da_401(api):
    c, _ = api
    assert c.get("/v1/eu", headers={"Authorization": "Bearer ras_abc.def"}).status_code == 401


# --- Q14: doador PJ também passa pela Receita (regras 6.3) -----------------------------------------
def test_doador_pj_com_cnpj_inexistente_ou_inativo_e_recusado(api):
    c, _ = api
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="fantasma@exemplo.com", documento=_cnpj_fora_da_receita()))
    assert r.status_code == 422 and "Receita" in r.json()["detail"]
    inativo = _cnpj_novo({"situacao_cadastral": 8, "descricao_situacao_cadastral": "BAIXADA"})
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="baixada@exemplo.com", documento=inativo))
    assert r.status_code == 422 and "ativo" in r.json()["detail"]


def test_doador_pj_com_receita_fora_do_ar_fica_pendente_e_nao_entra(api):
    c, modulo = api
    original = modulo.E.receita
    modulo.E.receita = ConsultaSimulada({}, indisponivel=True)
    try:
        r = c.post("/v1/auth/cadastro", json=_cadastro(email="pj-pendente@exemplo.com"))
    finally:
        modulo.E.receita = original
    assert r.status_code == 201 and r.json()["status"] == "pendente"
    assert _entrar(c, "pj-pendente@exemplo.com").status_code == 403


def test_doador_pj_fora_do_ramo_de_alimentos_vai_para_revisao_do_admin(api):
    c, _ = api
    loja = _cnpj_novo({"cnae_fiscal": 4751201})  # informática: não bloqueia, mas o admin revisa (6.3)
    r = c.post("/v1/auth/cadastro", json=_cadastro(email="loja@exemplo.com", documento=loja))
    assert r.status_code == 201 and r.json()["status"] == "pendente"
    login = _entrar(c, "loja@exemplo.com")
    assert login.status_code == 403 and "admin" in login.json()["detail"]


def test_doador_pf_nao_depende_da_receita(api):
    c, modulo = api
    original = modulo.E.receita
    modulo.E.receita = ConsultaSimulada({}, indisponivel=True)
    try:
        r = c.post("/v1/auth/cadastro", json=_cadastro(email="pf-sem-receita@exemplo.com", tipo_doador="PF",
                                                       documento="11144477735"))
    finally:
        modulo.E.receita = original
    assert r.status_code == 201 and r.json()["status"] == "ativa"

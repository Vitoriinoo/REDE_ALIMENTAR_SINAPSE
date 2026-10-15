"""Tela de entrada: Entrar (e-mail e senha) e Criar conta (Doador PF/PJ, ONG, Transportador).

A API é a única autoridade: papel e ID vêm da conta devolvida por /v1/auth/login, nunca de um menu.
As checagens daqui (CPF/CNPJ, tamanho da senha) só dão retorno rápido; a API valida de novo e é
ela que consulta a Receita para ONG e Doador PJ. Admin não se cadastra: é criado por script.
A senha nunca é guardada na sessão nem exibida; na sessão ficam só o token e {papel, id, nome}.
"""

from __future__ import annotations

import re
from collections.abc import MutableMapping

import streamlit as st

from src.dashboard import cliente_api, tema
from src.validacao.documentos import cnpj_valido, cpf_valido

SENHA_MIN = 10
PAPEIS_CADASTRO = {"doador": "Doador", "ong": "ONG", "transportador": "Transportador"}
AJUDA_CADASTRO = {
    "doador": "Restaurantes, mercados, padarias e pessoas físicas que doam alimentos.",
    "ong": "Instituições que recebem as doações. Exige CNPJ ativo na Receita Federal.",
    "transportador": "Motoristas de frete de retorno, voluntários ou entregadores pagos.",
}
TIPOS_DOADOR = {"PF": "Pessoa física (CPF)", "PJ": "Pessoa jurídica (CNPJ)"}
VEICULOS = {"moto": "Moto", "carro": "Carro", "utilitario": "Utilitário"}
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def documento_esperado(papel: str, tipo_doador: str | None = None) -> str:
    """CPF ou CNPJ, conforme o papel (ONG sempre CNPJ; transportador sempre CPF)."""
    if papel == "ong":
        return "CNPJ"
    if papel == "transportador":
        return "CPF"
    return "CPF" if tipo_doador == "PF" else "CNPJ"


def montar_cadastro(papel: str, nome: str, email: str, documento: str, senha: str,
                    tipo_doador: str | None = None, veiculo: str | None = None) -> dict:
    """Corpo de POST /v1/auth/cadastro, só com os campos do papel."""
    corpo = {"papel": papel, "email": email.strip().lower(), "senha": senha,
             "nome": nome.strip(), "documento": documento.strip()}
    if papel == "doador":
        corpo["tipo_doador"] = tipo_doador
    elif papel == "transportador":
        corpo["veiculo"] = veiculo
    return corpo


def problemas_cadastro(corpo: dict, confirmacao: str) -> list[str]:
    """Erros visíveis antes de chamar a API. Lista vazia = pode enviar."""
    papel = corpo.get("papel")
    erros = []
    if papel not in PAPEIS_CADASTRO:
        erros.append("Escolha Doador, ONG ou Transportador.")
    if not corpo.get("nome"):
        erros.append("Informe o nome.")
    if not _EMAIL.match(corpo.get("email", "")):
        erros.append("Informe um e-mail válido.")
    tipo_doc = documento_esperado(papel, corpo.get("tipo_doador"))
    valido = cpf_valido if tipo_doc == "CPF" else cnpj_valido
    if not valido(corpo.get("documento", "")):
        erros.append(f"{tipo_doc} inválido: confira os dígitos.")
    if papel == "doador" and corpo.get("tipo_doador") not in TIPOS_DOADOR:
        erros.append("Escolha pessoa física ou jurídica.")
    if papel == "transportador" and corpo.get("veiculo") not in VEICULOS:
        erros.append("Escolha o veículo: moto, carro ou utilitário.")
    senha = corpo.get("senha", "")
    if len(senha) < SENHA_MIN:
        erros.append(f"A senha precisa de pelo menos {SENHA_MIN} caracteres.")
    elif senha != confirmacao:
        erros.append("As senhas não conferem.")
    return erros


def concluir_entrada(resposta: dict, estado: MutableMapping) -> None:
    """Guarda na sessão só o necessário: identidade (vinda da API) e o token."""
    estado["ident"] = {"papel": resposta["papel"], "id": resposta["id"], "nome": resposta.get("nome") or resposta["id"]}
    estado["chave"] = resposta["token"]


def mensagem_login(erro: cliente_api.ErroAPI) -> str:
    if erro.status == 401:
        return "E-mail ou senha inválidos."
    if erro.status == 429:
        return "Muitas tentativas seguidas. Aguarde alguns minutos e tente de novo."
    if erro.status == 403:
        return f"Conta ainda não liberada: {erro.mensagem}"
    return erro.mensagem


def entrar(email: str, senha: str, estado: MutableMapping) -> str | None:
    """Faz o login pela API. Devolve a mensagem de erro, ou None se entrou."""
    try:
        resposta = cliente_api.entrar(email.strip().lower(), senha)
    except cliente_api.ErroAPI as e:
        return mensagem_login(e)
    concluir_entrada(resposta, estado)
    return None


def _aba_entrar() -> None:
    with st.form("entrar"):
        email = st.text_input("E-mail", placeholder="voce@exemplo.org")
        senha = st.text_input("Senha", type="password")
        if st.form_submit_button("Entrar", type="primary", use_container_width=True):
            if not email.strip() or not senha:
                st.error("Informe e-mail e senha.")
                return
            with st.spinner("Conferindo..."):
                erro = entrar(email, senha, st.session_state)
            if erro:
                st.error(erro)
            else:
                st.rerun()
    st.caption("Administradores recebem o acesso da equipe da plataforma.")


def _aba_cadastro() -> None:
    papel = st.radio("Quero participar como", list(PAPEIS_CADASTRO), format_func=PAPEIS_CADASTRO.get,
                     horizontal=True, key="cad_papel")
    st.caption(AJUDA_CADASTRO[papel])
    tipo_doador = None
    if papel == "doador":
        tipo_doador = st.radio("Tipo de doador", list(TIPOS_DOADOR), format_func=TIPOS_DOADOR.get,
                               horizontal=True, key="cad_tipo",
            help="Fica fixo na conta. Pessoa física só doa não perecível lacrado. "
                 "Pessoa jurídica passa pela consulta à Receita Federal.")
    tipo_doc = documento_esperado(papel, tipo_doador)

    with st.form(f"cadastro_{papel}"):
        nome = st.text_input("Nome da instituição" if papel == "ong" else
                             "Razão social ou nome fantasia" if tipo_doc == "CNPJ" else "Nome completo")
        email = st.text_input("E-mail")
        documento = st.text_input(tipo_doc, placeholder="Só números ou com pontuação")
        veiculo = None
        if papel == "transportador":
            veiculo = st.selectbox("Veículo", list(VEICULOS), format_func=VEICULOS.get)
        c1, c2 = st.columns(2)
        senha = c1.text_input("Senha", type="password", help=f"Mínimo de {SENHA_MIN} caracteres.")
        confirmacao = c2.text_input("Repita a senha", type="password")
        st.caption(f"Seu {tipo_doc} é usado só para validar o cadastro e fica guardado de forma "
                   "irreversível (HMAC), conforme a LGPD.")
        if not st.form_submit_button("Criar conta", type="primary", use_container_width=True):
            return

    corpo = montar_cadastro(papel, nome, email, documento, senha, tipo_doador, veiculo)
    erros = problemas_cadastro(corpo, confirmacao)
    if erros:
        for e in erros:
            st.error(e)
        return
    try:
        consulta_receita = papel == "ong" or (papel == "doador" and tipo_doador == "PJ")
        with st.spinner("Criando a conta" + (" e consultando a Receita Federal..." if consulta_receita else "...")):
            criada = cliente_api.cadastrar(corpo)
    except cliente_api.ErroAPI as e:
        st.error(f"Não foi possível criar a conta: {e.mensagem}")
        return
    if criada.get("status") == "pendente":
        st.warning("Conta criada, mas **pendente**: aguardando a verificação do CNPJ na Receita Federal "
                   "ou a revisão do administrador. Ela só é liberada depois dessa etapa.")
        return
    if entrar(corpo["email"], senha, st.session_state) is None:
        st.rerun()
    st.success("Conta criada. Entre pela aba **Entrar**.")


def desenhar() -> None:
    tema.cabecalho("Rede Alimenta IA", "Alimento que sobra encontra quem precisa, antes de vencer.")
    esq, dir_ = st.columns([5, 6], gap="large")
    with esq:
        tema.cartao("Doador", "<p>Cadastre o lote; a IA indica a ONG certa a tempo e gera a Declaração "
                    "de Doação assinada.</p>", "Restaurantes, mercados e pessoas físicas")
        tema.cartao("ONG", "<p>Receba ofertas compatíveis com sua capacidade e confirme a entrega.</p>",
                    "CNPJ ativo verificado na Receita")
        tema.cartao("Transportador", "<p>Veja suas corridas, o ponto de coleta e a rota pronta no mapa.</p>",
                    "Frete de retorno, voluntário ou entregador")
        st.caption("Quer só acompanhar? O **Painel de impacto** é público, no menu ao lado.")
    with dir_:
        aba_entrar, aba_cadastro = st.tabs(["Entrar", "Criar conta"])
        with aba_entrar:
            _aba_entrar()
        with aba_cadastro:
            _aba_cadastro()


if __name__ == "__main__":  # o Streamlit executa a página como __main__; importar nos testes não desenha
    desenhar()

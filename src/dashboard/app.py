"""Rede Alimenta IA: aplicação web (Streamlit).

- Entrar / Criar conta: e-mail e senha (Doador PF/PJ, ONG com CNPJ, Transportador). Admin é criado por script.
- Painel de impacto (público): impacto social, qualidade da IA, segurança, lotes ao vivo.
- Doador, ONG, Transportador e Admin: telas do papel, que operam a plataforma chamando a API.
- Documentos assinados (doador e admin): ver a Declaração de Doação e verificar a assinatura.

O papel vem da CONTA (devolvido pela API no login, junto com o token), não de um menu: quem entra
como doador não vê as telas de ONG nem de admin, e mesmo que tentasse, a API recusaria.

Uso local: streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `streamlit run` não põe a raiz no path

import streamlit as st

from src.dashboard import tema
from src.dashboard.dados import API_INTERNA

st.set_page_config(page_title="Rede Alimenta IA", layout="wide")
tema.aplicar_tema()

NOMES_PAPEL = {"doador": "Doador", "ong": "ONG", "transportador": "Transportador", "admin": "Administração"}


def paginas_do_papel(papel: str | None) -> list:
    """Menu por papel. Sem login: tela de entrada + painel público. Com login: a tela do papel abre primeiro."""
    painel = st.Page("paginas/painel.py", title="Painel de impacto")
    if papel is None:
        return [st.Page("paginas/login.py", title="Entrar ou criar conta", default=True), painel]
    documentos = st.Page("paginas/documentos.py", title="Documentos assinados")
    if papel == "doador":
        return [st.Page("paginas/doador.py", title="Doar alimentos", default=True), documentos, painel]
    if papel == "ong":
        return [st.Page("paginas/ong.py", title="ONG: ofertas, histórico e cadastro", default=True), painel]
    if papel == "transportador":
        return [st.Page("paginas/transportador.py", title="Minhas corridas", default=True), painel]
    if papel == "admin":
        return [st.Page("paginas/admin.py", title="Administração", default=True), documentos, painel]
    return [st.Page("paginas/painel.py", title="Painel de impacto", default=True)]  # papel desconhecido: só o público


ident = st.session_state.get("ident")
with st.sidebar:
    st.markdown("### Rede Alimenta IA")
    if ident:
        nome = escape(str(ident.get("nome") or ident.get("id", "")))
        papel_txt = escape(NOMES_PAPEL.get(ident.get("papel"), str(ident.get("papel"))))
        tema.cartao("Conectado", f"<p><strong>{nome}</strong><br>{papel_txt} · <code>{escape(str(ident.get('id', '')))}</code></p>")
        if st.button("Sair", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    else:
        st.caption("Entre com seu e-mail e senha para doar, receber ou transportar. "
                   "O painel de impacto é público.")
    st.caption(f"API: {urlsplit(API_INTERNA).netloc or API_INTERNA}")

st.navigation(paginas_do_papel((ident or {}).get("papel"))).run()

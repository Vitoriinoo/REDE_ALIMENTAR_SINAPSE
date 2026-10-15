"""Rede Alimenta IA: aplicação web (Streamlit).

- Painel de impacto (público): impacto social, qualidade da IA, segurança, lotes ao vivo.
- Doador, ONG e Admin (com chave de acesso): operam a plataforma chamando a API.

O papel vem da CHAVE (validada pela API em /v1/eu), não de um menu: quem entra com chave de doador
não vê as telas de ONG nem de admin, e mesmo que tentasse, a API recusaria.

Uso local: streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `streamlit run` não põe a raiz no path

import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar

st.set_page_config(page_title="Rede Alimenta IA", page_icon="🥫", layout="wide")
st.markdown(
    "<style>[data-testid='stMetricValue']{font-size:1.9rem} .block-container{padding-top:1.6rem}</style>",
    unsafe_allow_html=True)

NOMES_PAPEL = {"doador": "Doador", "ong": "ONG", "admin": "Administração"}

with st.sidebar:
    st.markdown("### 🥫 Rede Alimenta IA")
    ident = st.session_state.get("ident")
    if ident:
        st.success(f"Conectado como **{NOMES_PAPEL[ident['papel']]}** `{ident['id']}`")
        if st.button("Sair", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    else:
        with st.form("entrar", clear_on_submit=True):
            chave = st.text_input("Chave de acesso", type="password",
                                  help="Doadores, ONGs e administradores recebem uma chave própria.")
            if st.form_submit_button("Entrar", use_container_width=True) and chave:
                try:
                    st.session_state["ident"] = chamar("GET", "/v1/eu", chave.strip())
                    st.session_state["chave"] = chave.strip()
                    st.rerun()
                except ErroAPI as e:
                    st.error("Chave inválida." if e.status == 401 else e.mensagem)
        st.caption("Sem chave, só o painel público fica disponível.")

papel = (st.session_state.get("ident") or {}).get("papel")
paginas = [st.Page("paginas/painel.py", title="Painel de impacto", icon="📊", default=True)]
if papel == "doador":
    paginas.append(st.Page("paginas/doador.py", title="Doar alimentos", icon="🍲"))
elif papel == "ong":
    paginas.append(st.Page("paginas/ong.py", title="Ofertas da ONG", icon="🏠"))
elif papel == "admin":
    paginas.append(st.Page("paginas/admin.py", title="Administração", icon="🛡️"))

st.navigation(paginas).run()

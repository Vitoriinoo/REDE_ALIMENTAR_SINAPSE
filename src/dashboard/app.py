"""Rede Alimenta IA: aplicação web (Streamlit).

- Painel de impacto (público): impacto social, qualidade da IA, segurança, lotes ao vivo.
- Doador, ONG e Admin (entrada por perfil + chave de acesso): operam a plataforma chamando a API.
- Documentos assinados (doador e admin): ver a Declaração de Doação e verificar a assinatura.

O papel vem da CHAVE (validada pela API em /v1/eu), não de um menu: quem entra com chave de doador
não vê as telas de ONG nem de admin, e mesmo que tentasse, a API recusaria.

Uso local: streamlit run src/dashboard/app.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # `streamlit run` não põe a raiz no path

import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar
from src.dashboard.dados import API_INTERNA

st.set_page_config(page_title="Rede Alimenta IA", layout="wide")
st.markdown(
    "<style>[data-testid='stMetricValue']{font-size:1.9rem} .block-container{padding-top:1.6rem}</style>",
    unsafe_allow_html=True)

NOMES_PAPEL = {"doador": "Doador", "ong": "ONG", "admin": "Administração"}
AJUDA_PAPEL = {
    "doador": "Restaurantes, mercados, padarias e pessoas físicas que doam alimentos.",
    "ong": "Instituições que recebem as doações e confirmam a entrega.",
    "admin": "Equipe da plataforma: controle da IA, auditoria e documentos.",
}

with st.sidebar:
    st.markdown("### Rede Alimenta IA")
    ident = st.session_state.get("ident")
    if ident:
        st.success(f"Conectado como **{NOMES_PAPEL[ident['papel']]}** `{ident['id']}`")
        if st.button("Sair", use_container_width=True):
            st.session_state.clear()
            st.rerun()
    else:
        st.markdown("**Entrar**")
        escolhido = st.radio("Eu sou", list(NOMES_PAPEL), format_func=NOMES_PAPEL.get, horizontal=True)
        st.caption(AJUDA_PAPEL[escolhido])
        with st.form("entrar", clear_on_submit=True):
            chave = st.text_input(f"Chave de acesso ({NOMES_PAPEL[escolhido]})", type="password",
                                  help="Cada doador, ONG e administrador recebe uma chave própria.")
            # Aceita a linha inteira de segredos/chaves-api.txt ("doador:D-0008<TAB>ra_..."): vale o último trecho.
            chave = chave.split()[-1] if chave.strip() else ""
            if st.form_submit_button("Entrar", use_container_width=True) and chave:
                try:
                    quem = chamar("GET", "/v1/eu", chave)
                except ErroAPI as e:
                    if e.status == 401:
                        # Diagnóstico sem expor a chave: formato e tamanho (as chaves geradas têm ra_<papel>_ + 32).
                        dica = ("ela deve começar com ra_" if not chave.startswith("ra_")
                                else f"recebida com {len(chave)} caracteres; confira se copiou inteira")
                        st.error(f"Chave inválida: {dica}.")
                    else:
                        st.error(e.mensagem)
                else:
                    # O papel continua vindo da CHAVE (a API decide); a escolha só evita entrar no perfil errado.
                    if quem["papel"] != escolhido:
                        st.error(f"Esta chave não é de {NOMES_PAPEL[escolhido]}. Escolha o perfil certo acima.")
                    else:
                        st.session_state["ident"], st.session_state["chave"] = quem, chave
                        st.rerun()
        st.caption("Sem chave, só o painel público fica disponível.")
    st.caption(f"API: {urlsplit(API_INTERNA).netloc or API_INTERNA}")

papel = (st.session_state.get("ident") or {}).get("papel")
paginas = [st.Page("paginas/painel.py", title="Painel de impacto", default=True)]
if papel == "doador":
    paginas += [st.Page("paginas/doador.py", title="Doar alimentos"),
                st.Page("paginas/documentos.py", title="Documentos assinados")]
elif papel == "ong":
    paginas.append(st.Page("paginas/ong.py", title="ONG"))
elif papel == "admin":
    paginas += [st.Page("paginas/admin.py", title="Administração"),
                st.Page("paginas/documentos.py", title="Documentos assinados")]

st.navigation(paginas).run()

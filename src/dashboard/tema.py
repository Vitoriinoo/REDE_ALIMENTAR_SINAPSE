"""Identidade visual compartilhada por todas as telas do dashboard.

Toda página chama `aplicar_tema()` uma vez (o app.py já chama) e monta o topo com `cabecalho()`.
Cores, cartões e selos de prioridade saem daqui para as telas não divergirem.
"""

from __future__ import annotations

from html import escape

import streamlit as st

# Paleta: verde = alimento salvo, laranja = ação, vermelho/amarelo = alertas de validade.
VERDE = "#1f8a4c"
VERDE_CLARO = "#e8f5ee"
LARANJA = "#f08c00"
TINTA = "#1d2433"
TINTA_2 = "#4a5468"
MUDO = "#7b8496"
BORDA = "#e3e7ee"
FUNDO_CARTAO = "#ffffff"
STATUS = {"bom": "#0ca30c", "atencao": "#fab219", "critico": "#d03b3b"}
COR_PRIORIDADE = {"CRITICA": "#d03b3b", "ALTA": "#f08c00", "MEDIA": "#fab219", "BAIXA": "#1f8a4c"}
ROTULO_PRIORIDADE = {"CRITICA": "CRÍTICA", "ALTA": "ALTA", "MEDIA": "MÉDIA", "BAIXA": "BAIXA"}

_CSS = f"""
<style>
.block-container {{padding-top: 1.4rem; max-width: 1280px}}
[data-testid='stMetricValue'] {{font-size: 1.9rem}}
[data-testid='stSidebar'] {{background: {VERDE_CLARO}}}
.ra-cab h1 {{font-size: 1.9rem; margin: 0; color: {TINTA}}}
.ra-cab p {{color: {TINTA_2}; margin: .2rem 0 1rem}}
.ra-cartao {{background: {FUNDO_CARTAO}; border: 1px solid {BORDA}; border-radius: 14px;
            padding: 1rem 1.2rem; margin-bottom: .8rem; box-shadow: 0 1px 2px rgba(0,0,0,.04)}}
.ra-cartao h4 {{margin: 0 0 .3rem; color: {TINTA}}}
.ra-cartao .ra-sub {{color: {MUDO}; font-size: .88rem}}
.ra-selo {{display: inline-block; padding: .1rem .55rem; border-radius: 999px; color: #fff;
          font-size: .78rem; font-weight: 600; letter-spacing: .02em}}
.stButton > button[kind='primary'] {{background: {VERDE}; border-color: {VERDE}}}
</style>
"""


def aplicar_tema() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)


def cabecalho(titulo: str, subtitulo: str = "") -> None:
    sub = f"<p>{escape(subtitulo)}</p>" if subtitulo else ""
    st.markdown(f"<div class='ra-cab'><h1>{escape(titulo)}</h1>{sub}</div>", unsafe_allow_html=True)


def selo_prioridade(prioridade: str) -> str:
    """HTML de um selo colorido (CRÍTICA vermelho, ALTA laranja, MÉDIA amarelo, BAIXA verde)."""
    p = (prioridade or "").upper().replace("Í", "I").replace("É", "E")
    cor = COR_PRIORIDADE.get(p, MUDO)
    return f"<span class='ra-selo' style='background:{cor}'>{escape(ROTULO_PRIORIDADE.get(p, p))}</span>"


def cartao(titulo: str, corpo_html: str = "", sub: str = "") -> None:
    """Cartão com título, subtítulo opcional e corpo em HTML (o chamador escapa o que vier de usuário)."""
    sub_html = f"<div class='ra-sub'>{escape(sub)}</div>" if sub else ""
    st.markdown(f"<div class='ra-cartao'><h4>{escape(titulo)}</h4>{sub_html}{corpo_html}</div>",
                unsafe_allow_html=True)

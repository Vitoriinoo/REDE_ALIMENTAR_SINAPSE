"""Tela de administração: controle da IA (interruptor por modelo, regras 10.3) e lotes recentes.

Desligar um modelo não para o sistema: a regra assume (fallback) e a troca vai para o log de auditoria.
"""

from __future__ import annotations

from datetime import timedelta, timezone

import pandas as pd
import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar
from src.dashboard.dados import API_PUBLICA

BRASILIA = timezone(timedelta(hours=-3))
ident, chave = st.session_state.get("ident") or {}, st.session_state.get("chave")
if ident.get("papel") != "admin":
    st.warning("Entre com uma chave de administração na barra lateral.")
    st.stop()

NOMES = {"prioridade": "Modelo 1: prioridade do lote", "descarte": "Modelo 2: risco de descarte",
         "nlp": "NLP: sugestão de categoria (Hugging Face)"}

st.title("Administração")
st.caption(f"Admin `{ident['id']}` · documentação da API: {API_PUBLICA}/docs")

try:
    estado = chamar("GET", "/v1/ia", chave)
except ErroAPI as e:
    st.error(e.mensagem)
    st.stop()

st.subheader("Controle da IA")
st.caption(f"Onde a IA roda: **{'serviço isolado' if estado['onde_roda'] == 'servico_isolado' else 'mesmo processo da API'}**. "
           "Desligado, o sistema continua no ar com a regra no lugar do modelo.")
for modelo, nome in NOMES.items():
    with st.container(border=True):
        c = st.columns([3, 2, 3, 2])
        ligado = estado["ligados"].get(modelo, False)
        meta = (estado["modelos"] or {}).get({"prioridade": "m1", "descarte": "m2", "nlp": "nlp"}[modelo])
        c[0].markdown(f"**{nome}**  \n{'versão ' + meta['versao'] if meta and meta.get('versao') else 'não carregado'}")
        c[1].markdown("🟢 **ligado**" if ligado else "⚪ **desligado** (regra assume)")
        motivo = c[2].text_input("Motivo (vai para o log)", key=f"mot_{modelo}",
                                 placeholder="ex.: drift detectado, auditoria")
        if c[3].button("Desligar" if ligado else "Ligar", key=f"bt_{modelo}", use_container_width=True):
            if len(motivo.strip()) < 3:
                st.toast("Informe o motivo: toda troca é auditada.", icon="⚠️")
            else:
                try:
                    chamar("POST", "/v1/admin/ia", chave, {"modelo": modelo, "ligado": not ligado,
                                                           "motivo": motivo.strip()})
                    st.rerun()
                except ErroAPI as e:
                    st.toast(e.mensagem, icon="⚠️")

st.subheader("Lotes recentes (API)")
try:
    lotes = pd.DataFrame(chamar("GET", "/v1/lotes", chave))
except ErroAPI as e:
    st.error(e.mensagem)
    lotes = pd.DataFrame()
if lotes.empty:
    st.info("Nenhum lote cadastrado pela API ainda.")
else:
    lotes["ts_cadastro"] = pd.to_datetime(lotes["ts_cadastro"], utc=True).dt.tz_convert(BRASILIA).dt.strftime("%d/%m %H:%M")
    st.dataframe(lotes, hide_index=True, use_container_width=True)

"""Tela da ONG: ofertas da vez (oferta sequencial, regras 6.2), aceite/recusa, confirmação da entrega e histórico.

A ONG vê o alimento e a logística, nunca quem doou (minimização, regras 11).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar
from src.dashboard.dados import PRIORIDADE

BRASILIA = timezone(timedelta(hours=-3))
ident, chave = st.session_state.get("ident") or {}, st.session_state.get("chave")
if ident.get("papel") != "ong":
    st.warning("Entre com uma chave de ONG na barra lateral.")
    st.stop()

CATEGORIA = {"preparado": "Preparado", "refrigerado": "Refrigerado", "congelado": "Congelado",
             "hortifruti": "Hortifrúti", "padaria": "Padaria", "nao_perecivel": "Não perecível"}

st.title("ONG")
st.caption(f"ONG `{ident['id']}` · as ofertas atualizam sozinhas a cada 15 s")
aba_ofertas, aba_historico = st.tabs(["Ofertas e entregas", "Histórico de recebimentos"])


def _hora(valor) -> str:
    return datetime.fromisoformat(str(valor)).astimezone(BRASILIA).strftime("%d/%m %H:%M") if valor else "—"


def _agir(rota: str, corpo: dict | None, sucesso: str) -> None:
    try:
        r = chamar("POST", rota, chave, corpo)
        st.toast(sucesso.format(**r))
    except ErroAPI as e:
        st.toast(e.mensagem)


@st.fragment(run_every="15s")
def painel_ong() -> None:
    try:
        dados = chamar("GET", "/v1/ong/ofertas", chave)
    except ErroAPI as e:
        st.error(e.mensagem)
        return

    st.subheader(f"Ofertas para você ({len(dados['ofertas'])})")
    if not dados["ofertas"]:
        st.info("Nenhuma oferta aguardando sua resposta agora.")
    for o in dados["ofertas"]:
        with st.container(border=True):
            c = st.columns([3, 2, 2, 2])
            c[0].markdown(f"**{CATEGORIA.get(o['categoria'], o['categoria'])}** · {o['peso_kg']:.1f} kg  \n"
                          f"`{o['codigo']}` · doador em {o['regiao_doador']}")
            c[1].markdown(f"{PRIORIDADE.get(o['prioridade'], o['prioridade'])}  \nvence {_hora(o['validade_efetiva'])}")
            c[2].markdown(f"{o['km']:.1f} km · ~{o['minutos_ate_receber']:.0f} min  \n"
                          f"{'direto' if o['modo'] == 'direto' else 'via hub'} · ~{o['refeicoes_estimadas']:.0f} refeições")
            if c[3].button("Aceitar", key=f"ac_{o['codigo']}", type="primary", use_container_width=True):
                _agir(f"/v1/lotes/{o['codigo']}/aceite", None, "Aceito em {minutos_ate_match} min do cadastro.")
                st.rerun(scope="fragment")
            if c[3].button("Recusar", key=f"rc_{o['codigo']}", use_container_width=True):
                _agir(f"/v1/lotes/{o['codigo']}/recusa", None, "Recusado: oferta passou para {proxima_ong}.")
                st.rerun(scope="fragment")

    st.subheader(f"Aguardando entrega ({len(dados['aguardando_entrega'])})")
    if not dados["aguardando_entrega"]:
        st.info("Nenhum lote a caminho.")
    for o in dados["aguardando_entrega"]:
        with st.container(border=True):
            c = st.columns([3, 3, 2])
            c[0].markdown(f"**{CATEGORIA.get(o['categoria'], o['categoria'])}** · {o['peso_kg']:.1f} kg  \n"
                          f"`{o['codigo']}` · aceito {_hora(o['ts_aceite_ong'])}")
            aprovada = c[1].radio("Inspeção na chegada", ["Aprovada", "Reprovada"], key=f"in_{o['codigo']}",
                                  horizontal=True, help="Cheiro, temperatura, embalagem, validade (regras 6.2.1)")
            if c[2].button("Confirmar entrega", key=f"en_{o['codigo']}", type="primary", use_container_width=True):
                _agir(f"/v1/lotes/{o['codigo']}/entrega", {"inspecao_aprovada": aprovada == "Aprovada"},
                      "Entrega registrada: {status} · {refeicoes} refeições.")
                st.rerun(scope="fragment")


def historico() -> None:
    try:
        h = pd.DataFrame(chamar("GET", "/v1/ong/historico", chave))
    except ErroAPI as e:
        st.error(e.mensagem)
        return
    if h.empty:
        st.info("Nenhum recebimento registrado ainda. Lotes aparecem aqui depois da confirmação da entrega.")
        return
    entregues = h[h["status_final"] == "ENTREGUE"]
    c = st.columns(3)
    c[0].metric("Lotes recebidos", len(entregues))
    c[1].metric("kg recebidos", f"{entregues['peso_kg'].sum():.1f}".replace(".", ","))
    c[2].metric("Refeições", f"{entregues['refeicoes'].fillna(0).sum():.0f}")
    situacao = {"ENTREGUE": "Recebido", "DESCARTADO": "Recusado na inspeção"}
    st.dataframe(pd.DataFrame({
        "Lote": h["codigo"],
        "Alimento": h["categoria"].map(lambda c: CATEGORIA.get(c, c)),
        "Peso (kg)": h["peso_kg"].round(1),
        "Prioridade": h["prioridade"].map(lambda p: PRIORIDADE.get(p, p)),
        "Aceito em": h["ts_aceite_ong"].map(_hora),
        "Entregue em": h["ts_entrega"].map(_hora),
        "Situação": h["status_final"].map(lambda s: situacao.get(s, s)),
        "Refeições": h["refeicoes"].fillna(0).round(0),
    }), hide_index=True, use_container_width=True)
    st.caption("A ONG vê o alimento e o resultado, nunca quem doou (minimização, LGPD).")


with aba_ofertas:
    painel_ong()
with aba_historico:
    historico()

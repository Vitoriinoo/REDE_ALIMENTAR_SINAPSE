"""Tela do Transportador (somente leitura): corridas, mapa das rotas e rota no Google Maps.

O papel transportador ainda não tem ações na API (aceitar ou recusar corrida): é o próximo passo.
Aqui ele vê o que já lhe foi atribuído, com o ponto de coleta (doador ou hub) e a ONG de entrega.
"""

from __future__ import annotations

from html import escape

import pandas as pd
import pydeck as pdk
import streamlit as st

from src.dashboard import dados, tema

VEICULO = {"moto": "Moto", "carro": "Carro", "utilitario": "Utilitário", "van": "Van", "bicicleta": "Bicicleta"}
MODALIDADE = {"voluntario": "Voluntário", "motorista_retorno": "Frete de retorno", "transportadora": "Transportadora",
              "app_entrega": "Entregador pago (caixa solidário)", "ong_retira": "ONG retira",
              "doador_entrega": "Doador entrega", "ponto_encontro_hub": "Ponto de encontro no hub"}
COR_RGB = {"CRITICA": [208, 59, 59], "ALTA": [240, 140, 0], "MEDIA": [250, 178, 25], "BAIXA": [31, 138, 76]}

ident = st.session_state.get("ident") or {}
if ident.get("papel") != "transportador":
    st.warning("Entre com uma conta de Transportador para ver suas corridas.")
    st.stop()

tid = ident.get("id", "")
perfil = dados.transportador(tid)
nome = ident.get("nome") or tid
tema.cabecalho(f"Olá, {nome}", "Suas corridas: onde coletar, onde entregar e a rota pronta no Google Maps.")

if perfil:
    c = st.columns(4)
    c[0].metric("Modalidade", MODALIDADE.get(perfil["modalidade"], perfil["modalidade"]))
    c[1].metric("Veículo", VEICULO.get(perfil["veiculo"], perfil["veiculo"]))
    c[2].metric("Capacidade", f"{perfil['capacidade_kg']:.0f} kg")
    c[3].metric("Refrigerado", "Sim" if perfil["refrigerado"] else "Não")

corridas = dados.corridas_transportador(tid)
if corridas.empty:
    tema.cartao("Nenhuma corrida ainda",
                "<p>Quando um lote da sua região precisar de transporte, ele aparece aqui com a rota.</p>",
                sub="Contas novas começam sem histórico.")
    st.stop()

entregues = corridas[corridas["status_final"] == "ENTREGUE"]
m = st.columns(3)
m[0].metric("Corridas", f"{len(corridas)}")
m[1].metric("Alimento entregue", f"{entregues['peso_kg'].sum():,.0f} kg".replace(",", "."))
m[2].metric("Refeições geradas", f"{entregues['refeicoes'].sum():,.0f}".replace(",", "."))

st.subheader("Mapa das rotas")
ultimas = corridas.head(40).copy()
ultimas["cor"] = ultimas["prioridade"].map(lambda p: COR_RGB.get(p, [123, 132, 150]))
camadas = [
    pdk.Layer("ArcLayer", ultimas, get_source_position=["coleta_lon", "coleta_lat"],
              get_target_position=["entrega_lon", "entrega_lat"], get_source_color="cor",
              get_target_color=[31, 138, 76], get_width=3, pickable=True),
    pdk.Layer("ScatterplotLayer", ultimas, get_position=["coleta_lon", "coleta_lat"], get_fill_color="cor",
              get_radius=180, pickable=True),
    pdk.Layer("ScatterplotLayer", ultimas, get_position=["entrega_lon", "entrega_lat"],
              get_fill_color=[31, 138, 76], get_radius=180, pickable=True),
]
centro = pdk.ViewState(latitude=float(ultimas["coleta_lat"].mean()), longitude=float(ultimas["coleta_lon"].mean()),
                       zoom=10, pitch=35)
st.pydeck_chart(pdk.Deck(layers=camadas, initial_view_state=centro,
                         tooltip={"text": "{lote_id}\n{coleta_nome} -> ONG {ong_id}\n{peso_kg} kg · {categoria}"}))
st.caption("Arco: da coleta (cor da prioridade) até a ONG (verde). Últimas 40 corridas.")

st.subheader("Corridas")
filtro = st.segmented_control("Mostrar", ["Todas", "Entregues", "Descartadas", "Pendentes"], default="Todas")
mapa_filtro = {"Entregues": "ENTREGUE", "Descartadas": "DESCARTADO", "Pendentes": "PENDENTE"}
vista = corridas if filtro in (None, "Todas") else corridas[corridas["status_final"] == mapa_filtro[filtro]]

for _, r in vista.head(15).iterrows():
    rota = dados.link_google_maps((r["coleta_lat"], r["coleta_lon"]), (r["entrega_lat"], r["entrega_lon"]))
    horas = "" if pd.isna(r["horas_restantes"]) else f" · validade: {r['horas_restantes']:.1f} h no cadastro"
    corpo = (f"<p>{tema.selo_prioridade(r['prioridade'])} &nbsp;"
             f"<b>{r['peso_kg']:.1f} kg</b> de {escape(str(r['categoria']))}{escape(horas)}</p>"
             f"<p>Coleta: <b>{escape(r['coleta_nome'])}</b> &rarr; Entrega: <b>ONG {escape(str(r['ong_id']))}</b>"
             f" ({escape(str(r['regiao']))})</p>"
             f"<p><a href='{escape(rota)}' target='_blank' rel='noopener'>Abrir rota no Google Maps</a></p>")
    tema.cartao(f"Lote {r['lote_id']}", corpo,
                sub=f"{r['ts_cadastro']:%d/%m/%Y %H:%M} · {MODALIDADE.get(r['modalidade'], r['modalidade'])}"
                    f" · {str(r['status_final']).capitalize()}")
if len(vista) > 15:
    st.caption(f"Mostrando 15 de {len(vista)} corridas.")

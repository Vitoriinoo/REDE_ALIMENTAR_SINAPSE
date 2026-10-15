"""Página pública: impacto social, qualidade da IA e segurança (o painel da apresentação)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from src.dashboard import dados
from src.seguranca.stride import AMEACAS, nivel

# --- Paleta (referência validada: categórica em ordem fixa, sequencial azul, status reservado) ----
AZUL, LARANJA, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
SEQ_AZUL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
STATUS = {"bom": ("#0ca30c", "✔"), "atencao": ("#fab219", "▲"), "critico": ("#d03b3b", "✖")}
TINTA, TINTA_2, MUDO, GRADE, EIXO = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'

def layout(fig: go.Figure, altura: int = 340, legenda: bool = False) -> go.Figure:
    fig.update_layout(
        height=altura, margin=dict(l=8, r=8, t=72 if legenda else 36, b=8), paper_bgcolor="#fcfcfb", plot_bgcolor="#fcfcfb",
        font=dict(family=FONTE, color=TINTA_2, size=13), title_font=dict(color=TINTA, size=15),
        showlegend=legenda, legend=dict(orientation="h", y=1.0, yanchor="bottom", x=0, title=None),
        hoverlabel=dict(bgcolor="#ffffff", font=dict(family=FONTE, color=TINTA)),
    )
    fig.update_xaxes(gridcolor=GRADE, linecolor=EIXO, zeroline=False, tickfont=dict(color=MUDO))
    fig.update_yaxes(gridcolor=GRADE, linecolor=EIXO, zeroline=False, tickfont=dict(color=MUDO))
    return fig


def br(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor: float, casas: int = 1) -> str:
    return br(valor * 100, casas) + "%"


@st.cache_data(ttl=60, show_spinner=False)
def carregar():
    return dados.impacto_regiao(), dados.mensal(), dados.match_prioridade(), dados.calor()


st.title("Painel de impacto")
st.caption(f"IA + DevSecOps contra o desperdício de alimentos na Grande São Paulo · fonte: **{dados.fonte()}** · "
           "ano simulado set/2025–ago/2026 + lotes cadastrados ao vivo pela API")

regioes, mes, match, calor = carregar()
metricas = dados.relatorio("metricas_modelos.json") or {}
sast = dados.relatorio("sast/resumo.json") or {}

aba_impacto, aba_ia, aba_seg, aba_vivo = st.tabs(["Impacto social", "Qualidade da IA", "Segurança", "Ao vivo"])

# ============================== IMPACTO ==============================
with aba_impacto:
    kg, refeicoes = regioes["kg_salvos"].sum(), regioes["refeicoes"].sum()
    aceitos = regioes["entregues"].sum() + regioes["descartados"].sum()
    descarte = regioes["descartados"].sum() / aceitos if aceitos else 0
    mediana = float(match["mediana_min"].median()) if len(match) else 0
    media = (match["media_min"] * match["matches"]).sum() / match["matches"].sum() if len(match) else 0
    c = st.columns(4)
    c[0].metric("Alimento salvo", f"{br(kg / 1000, 1)} t", help="Soma do peso dos lotes com entrega confirmada")
    c[1].metric("Refeições geradas", br(refeicoes), help="kg × fator por categoria (WRAP 420 g; TACO ÷ 700 kcal/PAT)")
    c[2].metric("Taxa de descarte", pct(descarte), help="Lotes aceitos que se perderam (meta < 20%)")
    c[3].metric("Tempo mediano até o match", f"{br(mediana, 0)} min",
                help="Cadastro → aceite da ONG (mediana das prioridades). A média geral é puxada pelos lotes BAIXA, "
                     "que podem esperar horas")
    c[3].caption(f"média geral: {br(media, 0)} min · CRÍTICA primeiro")

    esq, dir_ = st.columns([3, 2])
    with esq:
        fig = px.density_map(calor, lat="lat", lon="lon", z="refeicoes", radius=30, zoom=9.2, opacity=0.8,
                             center={"lat": -23.58, "lon": -46.60}, map_style="carto-positron",
                             color_continuous_scale=SEQ_AZUL, hover_data={"kg_salvos": ":,.0f", "refeicoes": ":,.0f"},
                             title="Mapa de calor: onde as refeições chegaram (local da ONG, grade de ~1 km)")
        fig.update_coloraxes(colorbar=dict(title="refeições", thickness=10))
        st.plotly_chart(layout(fig, 460), use_container_width=True)
    with dir_:
        r = regioes.sort_values("refeicoes")
        fig = px.bar(r, x="refeicoes", y="regiao", orientation="h", color="indice_vulnerabilidade",
                     color_continuous_scale=SEQ_AZUL, range_color=(0, 1),
                     hover_data={"kg_salvos": ":,.0f", "indice_vulnerabilidade": ":.2f", "regiao": False},
                     labels={"refeicoes": "refeições", "regiao": "", "indice_vulnerabilidade": "vulnerab."},
                     title="Refeições por região de destino (cor = vulnerabilidade IPVS)")
        fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2)
        fig.update_coloraxes(colorbar=dict(title="IPVS", thickness=10))
        st.plotly_chart(layout(fig, 460), use_container_width=True)

    m = mes[mes["origem"] == "simulacao"].groupby("mes", as_index=False)[["refeicoes", "kg_salvos", "lotes_aceitos", "descartados"]].sum()
    m["taxa_descarte"] = m["descartados"] / m["lotes_aceitos"]
    a, b = st.columns(2)
    with a:
        fig = px.line(m, x="mes", y="refeicoes", markers=True, title="Refeições por mês",
                      labels={"mes": "", "refeicoes": "refeições"})
        fig.update_traces(line=dict(color=AZUL, width=2), marker=dict(size=8, line=dict(color="#fcfcfb", width=2)))
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(layout(fig), use_container_width=True)
    with b:
        fig = px.line(m, x="mes", y="taxa_descarte", markers=True, title="Taxa de descarte por mês (meta < 20%)",
                      labels={"mes": "", "taxa_descarte": "descarte"})
        fig.update_traces(line=dict(color=LARANJA, width=2), marker=dict(size=8, line=dict(color="#fcfcfb", width=2)))
        fig.add_hline(y=0.20, line_dash="dot", line_color=MUDO, annotation_text="meta 20%",
                      annotation_font_color=TINTA_2)
        fig.update_yaxes(tickformat=".0%", rangemode="tozero")
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(layout(fig), use_container_width=True)

    with st.expander("Tabela por região"):
        st.dataframe(regioes.drop(columns=["lat", "lon"]).sort_values("refeicoes", ascending=False),
                     hide_index=True, use_container_width=True)

# ============================== IA ==============================
with aba_ia:
    m1 = metricas.get("modelo_1_prioridade", {}).get("teste", {})
    m2 = metricas.get("modelo_2_descarte", {}).get("teste", {})
    nlp = (dados.relatorio("avaliacao_nlp.json") or {}).get("classificador_padrao", {}).get("teste_dataset", {})
    c = st.columns(4)
    c[0].metric("M1 prioridade: acurácia", pct(m1.get("acuracia", 0)),
                help="Teste temporal jun–ago/2026. O rótulo é regra + ~9% de discordância humana: ~92% é o teto")
    c[1].metric("M1: recall da CRÍTICA", pct(m1.get("recall_critica", 0)), help="Meta ≥ 90%. Piso de segurança: o modelo nunca rebaixa uma CRÍTICA")
    c[2].metric("M2 descarte: recall", pct(m2.get("recall", 0)), help="Meta ≥ 85% (achar o lote que vai se perder)")
    c[3].metric("NLP: acurácia da categoria", pct(nlp.get("acuracia_categoria", 0)),
                help="Embeddings HF (MiniLM multilíngue) + exemplos; é só sugestão, o doador confirma")

    a, b = st.columns(2)
    with a:
        h = m2.get("heuristica_v0_no_teste", {})
        comp = pd.DataFrame({
            "métrica": ["Recall", "Precisão", "ROC-AUC", "PR-AUC"] * 2,
            "valor": [m2.get("recall", 0), m2.get("precisao", 0), m2.get("roc_auc", 0), m2.get("pr_auc", 0),
                      h.get("recall", 0), h.get("precisao", 0), h.get("roc_auc", 0), h.get("pr_auc", 0)],
            "quem": ["Modelo 2 (Random Forest)"] * 4 + ["Heurística sem IA"] * 4,
        })
        fig = px.bar(comp, x="métrica", y="valor", color="quem", barmode="group", text_auto=".2f",
                     color_discrete_sequence=[AZUL, LARANJA], title="Modelo 2 × heurística (conjunto de teste)",
                     labels={"valor": "", "métrica": ""})
        fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2, textfont_color=TINTA_2,
                          textposition="outside")
        fig.update_yaxes(range=[0, 1.08], tickformat=".0%")
        st.plotly_chart(layout(fig, 360, legenda=True), use_container_width=True)
    with b:
        mc = m1.get("matriz_confusao", {})
        if mc:
            fig = px.imshow(mc["valores"], x=mc["ordem"], y=mc["ordem"], text_auto=True,
                            color_continuous_scale=SEQ_AZUL, labels=dict(x="previsto", y="real", color="lotes"),
                            title="Modelo 1: matriz de confusão (teste)")
            fig.update_traces(xgap=2, ygap=2)
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(layout(fig, 360), use_container_width=True)

    a, b = st.columns(2)
    with a:
        ordem = ["CRITICA", "ALTA", "MEDIA", "BAIXA"]
        mp = match.set_index("prioridade").reindex(ordem).reset_index()
        fig = px.bar(mp, x="prioridade", y="mediana_min", text_auto=".0f",
                     title="Tempo mediano até o match por prioridade (min)",
                     labels={"prioridade": "", "mediana_min": "minutos"},
                     hover_data={"media_min": ":.0f", "matches": ":,"})
        fig.update_traces(marker_color=AZUL, marker_line_color="#fcfcfb", marker_line_width=2,
                          textposition="outside", textfont_color=TINTA_2)
        st.plotly_chart(layout(fig), use_container_width=True)
    with b:
        imp = metricas.get("modelo_2_descarte", {}).get("importancia_permutacao", {})
        if imp:
            s = pd.Series(imp).sort_values().tail(8).reset_index()
            s.columns = ["feature", "importancia"]
            fig = px.bar(s, x="importancia", y="feature", orientation="h",
                         title="Modelo 2: o que mais pesa (importância por permutação)",
                         labels={"importancia": "queda no PR-AUC", "feature": ""})
            fig.update_traces(marker_color=AZUL, marker_line_color="#fcfcfb", marker_line_width=2)
            st.plotly_chart(layout(fig), use_container_width=True)
    st.caption("Split temporal: treino set/2025–fev/2026, validação mar–mai/2026 (escolha de modelo e limiar), "
               "teste jun–ago/2026. A IA só recomenda: piso de segurança, interruptor por modelo e fallback para a regra.")

# ============================== SEGURANÇA ==============================
with aba_seg:
    ba, bd = sast.get("bandit", {}).get("antes", {}), sast.get("bandit", {}).get("depois", {})
    trivy = sast.get("trivy", {})
    achados_antes = sum(ba.values()) + sum(sum(t["antes"].values()) for t in trivy.values())
    achados_depois = sum(bd.values()) + sum(sum(t["depois"].values()) for t in trivy.values())
    gate = sast.get("gate", {})
    cor, icone = STATUS["bom"] if gate.get("aprovado") else STATUS["critico"]
    c = st.columns(4)
    c[0].metric("Vulnerabilidades mitigadas (SAST)", br(max(achados_antes - achados_depois, 0)),
                help="Bandit (código) + Trivy (imagens e dependências): primeira varredura × atual")
    c[1].metric("Achados abertos", br(achados_depois), help="Todas as severidades, na varredura atual")
    stride_res = [nivel(a.residual) for a in AMEACAS]
    c[2].metric("STRIDE: ameaças mapeadas", len(AMEACAS))
    c[2].caption(f"{sum(n in ('Alto', 'Crítico') for n in stride_res)} altas/críticas no risco residual")
    c[3].markdown(
        f"<div style='padding-top:.2rem;color:{TINTA_2};font-size:.9rem'>Security gate do pipeline</div>"
        f"<div style='font-size:1.6rem;color:{TINTA}'><span style='color:{cor}'>{icone}</span> "
        f"{'Aprovado' if gate.get('aprovado') else 'Reprovado'}</div>"
        f"<div style='color:{MUDO};font-size:.8rem'>{gate.get('regra', '')}</div>", unsafe_allow_html=True)

    a, b = st.columns(2)
    with a:
        linhas = []
        for sev, rot in (("CRITICAL", "Crítica"), ("HIGH", "Alta"), ("MEDIUM", "Média"), ("LOW", "Baixa")):
            antes = ba.get(sev, 0) + sum(t["antes"].get(sev, 0) for t in trivy.values())
            depois = bd.get(sev, 0) + sum(t["depois"].get(sev, 0) for t in trivy.values())
            linhas += [{"severidade": rot, "varredura": "Primeira varredura", "achados": antes},
                       {"severidade": rot, "varredura": "Atual", "achados": depois}]
        fig = px.bar(pd.DataFrame(linhas), x="severidade", y="achados", color="varredura", barmode="group",
                     text_auto=True, color_discrete_sequence=[LARANJA, AZUL],
                     title="Achados SAST por severidade: antes × depois", labels={"severidade": "", "achados": ""})
        fig.update_traces(marker_line_color="#fcfcfb", marker_line_width=2, textposition="outside",
                          textfont_color=TINTA_2)
        st.plotly_chart(layout(fig, 360, legenda=True), use_container_width=True)
    with b:
        grade = pd.DataFrame(0, index=range(5, 0, -1), columns=range(1, 6))
        for a_ in AMEACAS:
            grade.loc[a_.i_res, a_.p_res] += 1
        fig = px.imshow(grade.values, x=[f"P{p}" for p in grade.columns], y=[f"I{i}" for i in grade.index],
                        text_auto=True, color_continuous_scale=SEQ_AZUL,
                        title="STRIDE residual: ameaças por Probabilidade × Impacto",
                        labels=dict(color="ameaças"))
        fig.update_traces(xgap=2, ygap=2)
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(layout(fig, 360), use_container_width=True)

    mit = pd.DataFrame(sast.get("mitigados", []))
    if len(mit):
        st.subheader("O que foi corrigido")
        st.dataframe(mit[["ferramenta", "regra", "severidade", "arquivo", "risco", "correcao"]], hide_index=True,
                     use_container_width=True)

    obs = dados.relatorio("observabilidade_demo.json") or {}
    guard = (dados.relatorio("avaliacao_nlp.json") or {}).get("guardrail", {}).get("v2", {})
    a, b = st.columns(2)
    with a:
        st.subheader("Observabilidade (anomalias injetadas)")
        inj = pd.DataFrame(obs.get("anomalias_injetadas", []))
        if len(inj):
            inj["detectado"] = inj["detectado"].map({True: "✔ detectada", False: "✖ não detectada"})
            st.dataframe(inj[["anomalia", "detectado", "nivel"]], hide_index=True, use_container_width=True)
    with b:
        st.subheader("Guardrail de entrada (texto livre)")
        if guard:
            st.dataframe(pd.DataFrame({"teste": list(guard), "resultado": list(guard.values())}), hide_index=True,
                         use_container_width=True)
            st.caption("Conjunto B nunca foi usado para ajustar: o que passa é risco residual, contido pela arquitetura "
                       "(a IA não tem agência e o doador confirma a categoria).")

# ============================== AO VIVO ==============================
with aba_vivo:
    @st.fragment(run_every="20s")
    def ao_vivo():
        st.caption("Lotes cadastrados pela API pública (atualiza a cada 20 s).")
        r = dados.recentes()
        if r.empty:
            st.info("Nenhum lote ao vivo ainda. Cadastre um pelo Swagger da API: "
                    f"{dados.API_PUBLICA}/docs")
        else:
            c = st.columns(3)
            c[0].metric("Lotes ao vivo", len(r))
            c[1].metric("kg cadastrados", br(r["peso_kg"].sum(), 1))
            c[2].metric("Entregues", int((r["status_final"] == "ENTREGUE").sum()))
            st.dataframe(r, hide_index=True, use_container_width=True)

    ao_vivo()

st.caption("Código: github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE · Projeto Integrador FIAP 2026 · Prof. Oerton Fernandes")

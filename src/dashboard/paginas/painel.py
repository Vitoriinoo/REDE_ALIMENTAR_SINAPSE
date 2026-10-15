"""Página pública: impacto social, qualidade da IA e segurança (o painel da apresentação)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from html import escape

from src.dashboard import dados
from src.dashboard.tema import (BORDA, COR_PRIORIDADE, LARANJA, MUDO, STATUS, TINTA, TINTA_2, VERDE, VERDE_CLARO,
                                aplicar_tema, cabecalho, cartao, selo_prioridade)
from src.seguranca.stride import AMEACAS, nivel

# --- Paleta dos gráficos: série principal verde (alimento salvo), comparação laranja, sequencial verde ---
SEQ_VERDE = ["#e8f5ee", "#c2e5d0", "#93cfae", "#62b588", "#3a9a66", "#1f8a4c", "#125c32"]
FUNDO, GRADE, EIXO = "#ffffff", "#eef1f5", BORDA
FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def layout(fig: go.Figure, altura: int = 340, legenda: bool = False) -> go.Figure:
    fig.update_layout(
        height=altura, margin=dict(l=8, r=8, t=72 if legenda else 36, b=8), paper_bgcolor=FUNDO, plot_bgcolor=FUNDO,
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
    return dados.impacto_regiao(), dados.mensal(), dados.match_prioridade(), dados.calor(), dados.match_geral()


aplicar_tema()
cabecalho("Painel de impacto", "IA + DevSecOps contra o desperdício de alimentos na Grande São Paulo")
st.caption(f"Fonte: **{dados.fonte()}** · ano simulado set/2025–ago/2026 + lotes cadastrados ao vivo pela API")

regioes, mes, match, calor, geral = carregar()
metricas = dados.relatorio("metricas_modelos.json") or {}
sast = dados.relatorio("sast/resumo.json") or {}

# Dados consolidados para o Resumo da banca
resumo = dados.resumo_banca()
kg_total = resumo["kg_salvos"]
refeicoes_total = resumo["refeicoes"]
acuracia_ia = resumo["acuracia_ia"]
tempo_tipico_match = resumo["tempo_tipico_min"]
mitigadas_total = resumo["vulnerabilidades_mitigadas"]


def cartao_banca(titulo: str, valor: str, frase: str, aba_nome: str) -> None:
    """Cartão grande com número destacado, frase simples e aba onde o detalhe aparece."""
    corpo = (
        f"<div style='font-size: 1.85rem; font-weight: 700; color: {VERDE}; margin: 0.2rem 0 0.35rem'>"
        f"{escape(valor)}</div>"
        f"<div style='color: {TINTA_2}; font-size: 0.86rem; line-height: 1.35; min-height: 2.7rem'>"
        f"{escape(frase)}</div>"
        f"<div style='margin-top: 0.5rem; font-size: 0.78rem; font-weight: 600; color: {MUDO}'>"
        f"Detalhe na aba: <span style='color: {VERDE}'>{escape(aba_nome)}</span></div>"
    )
    cartao(titulo, corpo)


st.subheader("Resumo para a banca")
cb1, cb2, cb3, cb4, cb5 = st.columns(5)
with cb1:
    cartao_banca(
        "Alimentos salvos",
        f"{br(kg_total / 1000, 1)} t",
        "Comida própria para consumo resgatada do desperdício.",
        "Impacto social",
    )
with cb2:
    cartao_banca(
        "Refeições geradas",
        br(refeicoes_total),
        "Refeições distribuídas nas 15 regiões atendidas.",
        "Impacto social",
    )
with cb3:
    cartao_banca(
        "Acurácia da IA",
        pct(acuracia_ia),
        "Acerto na priorização de atendimento dos lotes.",
        "Qualidade da IA",
    )
with cb4:
    cartao_banca(
        "Tempo típico de match",
        f"{br(tempo_tipico_match, 1)} min",
        "Tempo típico (mediana) entre cadastro e aceite da ONG.",
        "Impacto social",
    )
with cb5:
    cartao_banca(
        "Vulnerabilidades mitigadas",
        br(mitigadas_total),
        "Falhas de segurança eliminadas no código e imagens (22 para 0).",
        "Segurança",
    )

st.markdown(
    f"<div class='ra-cartao' style='background:{VERDE_CLARO};border-color:{BORDA};margin-top:.3rem;margin-bottom:.8rem'>"
    f"<strong style='color:{TINTA}'>Formatos da avaliação exigidos pela banca:</strong>"
    f"<div style='margin-top:.4rem;display:grid;grid-template-columns:repeat(auto-fit, minmax(260px, 1fr));gap:.6rem;color:{TINTA_2};font-size:.88rem'>"
    f"<div><strong>Gráficos dinâmicos:</strong> na aba <em>Ao vivo</em> (pulsação da rede com atualização automática a cada 20 s) e na aba <em>Impacto social</em> (evolução mensal interativa).</div>"
    f"<div><strong>Mapa de calor:</strong> na aba <em>Impacto social</em> (onde as refeições chegaram, grade geográfica de ~1 km).</div>"
    f"<div><strong>Indicadores de segurança:</strong> na aba <em>Segurança</em> (auditoria SAST Bandit + Trivy antes e depois, matriz STRIDE e security gate).</div>"
    f"</div></div>",
    unsafe_allow_html=True,
)

with st.expander("Entregáveis do projeto (10 itens do enunciado)", expanded=False):
    st.markdown(
        """
| Entregável | O que é (em linguagem simples) | Onde está no repositório |
|---|---|---|
| **1. Dataset** | Base de 24 mil lotes de doação calibrada com fontes públicas (IPVS/SEADE, TACO, PAT e WRAP) | [`data/processed/`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/tree/main/data/processed) e [`data/reference/`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/tree/main/data/reference) |
| **2. Modelo local** | Modelos de IA treinados localmente (M1 prioridade de atendimento e M2 risco de descarte) | [`src/models/`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/tree/main/src/models) e [métricas](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/reports/metricas_modelos.json) |
| **3. STRIDE** | Matriz de riscos e ameaças com 34 cenários avaliados por Probabilidade e Impacto com reteste | [`docs/stride/matriz-stride.md`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/docs/stride/matriz-stride.md) e [planilha](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/docs/stride/matriz-stride.xlsx) |
| **4. Dockerfile + Compose** | Containers isolados para API, inferência e painel, com imagens seguras sem usuário root | [`Dockerfile`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/Dockerfile) e [`docker-compose.yml`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/docker-compose.yml) |
| **5. CI/CD GitHub Actions** | Pipeline automatizado que executa testes e varreduras de segurança a cada alteração de código | [`.github/workflows/ci.yml`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/.github/workflows/ci.yml) |
| **6. SAST Bandit + Trivy** | Relatórios de varredura estática de código e containers: 22 vulnerabilidades eliminadas (zero abertas) | [`reports/sast/`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/tree/main/reports/sast) e [resumo](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/reports/sast/resumo.json) |
| **7. URL pública** | Sistema publicado na nuvem pública gratuita com documentação interativa da API e painel web | [Painel Streamlit](https://rede-alimenta-ia.streamlit.app/) e [API Render](https://rede-alimenta-ia-api-d5dk.onrender.com/docs) ([README](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/README.md)) |
| **8. Banco Supabase** | Banco PostgreSQL na nuvem com separação de papéis por menor privilégio e auditoria imutável | [`db/schema.sql`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/db/schema.sql) e [script de carga](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/src/db/carregar.py) |
| **9. README** | Documentação técnica completa com arquitetura, instruções de execução e evidências de entrega | [`README.md`](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/README.md) |
| **10. Pitch** | Estrutura da apresentação em sala com 12 tópicos cobrindo impacto social, IA e DevSecOps | [Seção Pitch no README](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/README.md#apresenta%C3%A7%C3%A3o-e-defesa-pitch) e [CONTEXTO §3.2](https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE/blob/main/CONTEXTO.md#32-entreg%C3%A1veis--arquivo--situa%C3%A7%C3%A3o) |
"""
    )

aba_impacto, aba_ia, aba_seg, aba_vivo = st.tabs(["Impacto social", "Qualidade da IA", "Segurança", "Ao vivo"])

# ============================== IMPACTO ==============================
with aba_impacto:
    kg, refeicoes = regioes["kg_salvos"].sum(), regioes["refeicoes"].sum()
    aceitos = regioes["entregues"].sum() + regioes["descartados"].sum()
    descarte = regioes["descartados"].sum() / aceitos if aceitos else 0
    mediana, media = geral["mediana_min"], geral["media_min"]
    c = st.columns(4)
    c[0].metric("Alimento salvo", f"{br(kg / 1000, 1)} t", help="Soma do peso dos lotes com entrega confirmada")
    c[1].metric("Refeições geradas", br(refeicoes), help="kg × fator por categoria (WRAP 420 g; TACO ÷ 700 kcal/PAT)")
    c[2].metric("Taxa de descarte", pct(descarte), help="Lotes aceitos que se perderam (meta < 20%)")
    c[3].metric("Tempo típico até o match", f"{br(mediana, 1)} min",
                help="Cadastro até o aceite da ONG (mediana de todos os matches). A média geral é puxada pelos lotes BAIXA, "
                     "que podem esperar horas")
    c[3].caption(f"mediana: {br(mediana, 1)} min · média geral: {br(media, 0)} min · CRÍTICA primeiro")

    esq, dir_ = st.columns([3, 2])
    with esq:
        st.caption("Mapa de calor da carência atendida: concentração de refeições onde a comida chegou (grade de ~1 km).")
        fig = px.density_map(calor, lat="lat", lon="lon", z="refeicoes", radius=30, zoom=9.2, opacity=0.8,
                             center={"lat": -23.58, "lon": -46.60}, map_style="carto-positron",
                             color_continuous_scale=SEQ_VERDE, hover_data={"kg_salvos": ":,.0f", "refeicoes": ":,.0f"},
                             title="Mapa de calor: onde as refeições chegaram (local da ONG, grade de ~1 km)")
        fig.update_coloraxes(colorbar=dict(title="refeições", thickness=10))
        st.plotly_chart(layout(fig, 460), use_container_width=True)
    with dir_:
        st.caption("Distribuição por região e índice de vulnerabilidade social IPVS.")
        r = regioes.sort_values("refeicoes")
        fig = px.bar(r, x="refeicoes", y="regiao", orientation="h", color="indice_vulnerabilidade",
                     color_continuous_scale=SEQ_VERDE, range_color=(0, 1),
                     hover_data={"kg_salvos": ":,.0f", "indice_vulnerabilidade": ":.2f", "regiao": False},
                     labels={"refeicoes": "refeições", "regiao": "", "indice_vulnerabilidade": "vulnerab."},
                     title="Refeições por região de destino (cor = vulnerabilidade IPVS)")
        fig.update_traces(marker_line_color=FUNDO, marker_line_width=2)
        fig.update_coloraxes(colorbar=dict(title="IPVS", thickness=10))
        st.plotly_chart(layout(fig, 460), use_container_width=True)

    m = mes[mes["origem"] == "simulacao"].groupby("mes", as_index=False)[["refeicoes", "kg_salvos", "lotes_aceitos", "descartados"]].sum()
    m["taxa_descarte"] = m["descartados"] / m["lotes_aceitos"]
    st.caption("Gráficos dinâmicos de evolução mensal: acompanhamento mês a mês das refeições e da taxa de descarte.")
    a, b = st.columns(2)
    with a:
        fig = px.line(m, x="mes", y="refeicoes", markers=True, title="Refeições por mês",
                      labels={"mes": "", "refeicoes": "refeições"})
        fig.update_traces(line=dict(color=VERDE, width=2), marker=dict(size=8, line=dict(color=FUNDO, width=2)))
        fig.update_layout(hovermode="x unified")
        st.plotly_chart(layout(fig), use_container_width=True)
    with b:
        fig = px.line(m, x="mes", y="taxa_descarte", markers=True, title="Taxa de descarte por mês (meta < 20%)",
                      labels={"mes": "", "taxa_descarte": "descarte"})
        fig.update_traces(line=dict(color=LARANJA, width=2), marker=dict(size=8, line=dict(color=FUNDO, width=2)))
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
                     color_discrete_sequence=[VERDE, LARANJA], title="Modelo 2 × heurística (conjunto de teste)",
                     labels={"valor": "", "métrica": ""})
        fig.update_traces(marker_line_color=FUNDO, marker_line_width=2, textfont_color=TINTA_2,
                          textposition="outside")
        fig.update_yaxes(range=[0, 1.08], tickformat=".0%")
        st.plotly_chart(layout(fig, 360, legenda=True), use_container_width=True)
    with b:
        mc = m1.get("matriz_confusao", {})
        if mc:
            fig = px.imshow(mc["valores"], x=mc["ordem"], y=mc["ordem"], text_auto=True,
                            color_continuous_scale=SEQ_VERDE, labels=dict(x="previsto", y="real", color="lotes"),
                            title="Modelo 1: matriz de confusão (teste)")
            fig.update_traces(xgap=2, ygap=2)
            fig.update_coloraxes(showscale=False)
            st.plotly_chart(layout(fig, 360), use_container_width=True)

    a, b = st.columns(2)
    with a:
        ordem = ["CRITICA", "ALTA", "MEDIA", "BAIXA"]
        mp = match.set_index("prioridade").reindex(ordem).reset_index()
        fig = px.bar(mp, x="prioridade", y="mediana_min", text_auto=".0f",
                     title="Tempo típico até o match por prioridade (min)",
                     labels={"prioridade": "", "mediana_min": "minutos"},
                     hover_data={"media_min": ":.0f", "matches": ":,"})
        fig.update_traces(marker_color=VERDE, marker_line_color=FUNDO, marker_line_width=2,
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
            fig.update_traces(marker_color=VERDE, marker_line_color=FUNDO, marker_line_width=2)
            st.plotly_chart(layout(fig), use_container_width=True)
    st.caption("Split temporal: treino set/2025–fev/2026, validação mar–mai/2026 (escolha de modelo e limiar), "
               "teste jun–ago/2026. A IA só recomenda: piso de segurança, interruptor por modelo e fallback para a regra.")

# ============================== SEGURANÇA ==============================
with aba_seg:
    st.caption("Indicadores de segurança: relatórios SAST (Bandit e Trivy), matriz STRIDE e security gate do pipeline CI/CD.")
    ba, bd = sast.get("bandit", {}).get("antes", {}), sast.get("bandit", {}).get("depois", {})
    trivy = sast.get("trivy", {})
    achados_antes = sum(ba.values()) + sum(sum(t["antes"].values()) for t in trivy.values())
    achados_depois = sum(bd.values()) + sum(sum(t["depois"].values()) for t in trivy.values())
    gate = sast.get("gate", {})
    cor = STATUS["bom"] if gate.get("aprovado") else STATUS["critico"]
    c = st.columns(4)
    c[0].metric("Vulnerabilidades mitigadas (SAST)", br(max(achados_antes - achados_depois, 0)),
                help="Bandit (código) + Trivy (imagens e dependências): primeira varredura × atual")
    c[1].metric("Achados abertos", br(achados_depois), help="Todas as severidades, na varredura atual")
    stride_res = [nivel(a.residual) for a in AMEACAS]
    c[2].metric("STRIDE: ameaças mapeadas", len(AMEACAS))
    c[2].caption(f"{sum(n in ('Alto', 'Crítico') for n in stride_res)} altas/críticas no risco residual")
    with c[3]:
        cartao("Security gate do pipeline",
               f"<span class='ra-selo' style='background:{cor};font-size:.95rem'>"
               f"{'Aprovado' if gate.get('aprovado') else 'Reprovado'}</span>"
               f"<div class='ra-sub' style='margin-top:.4rem'>{escape(str(gate.get('regra', '')))}</div>")

    a, b = st.columns(2)
    with a:
        linhas = []
        for sev, rot in (("CRITICAL", "Crítica"), ("HIGH", "Alta"), ("MEDIUM", "Média"), ("LOW", "Baixa")):
            antes = ba.get(sev, 0) + sum(t["antes"].get(sev, 0) for t in trivy.values())
            depois = bd.get(sev, 0) + sum(t["depois"].get(sev, 0) for t in trivy.values())
            linhas += [{"severidade": rot, "varredura": "Primeira varredura", "achados": antes},
                       {"severidade": rot, "varredura": "Atual", "achados": depois}]
        fig = px.bar(pd.DataFrame(linhas), x="severidade", y="achados", color="varredura", barmode="group",
                     text_auto=True, color_discrete_sequence=[LARANJA, VERDE],
                     title="Achados SAST por severidade: antes × depois", labels={"severidade": "", "achados": ""})
        fig.update_traces(marker_line_color=FUNDO, marker_line_width=2, textposition="outside",
                          textfont_color=TINTA_2)
        st.plotly_chart(layout(fig, 360, legenda=True), use_container_width=True)
    with b:
        grade = pd.DataFrame(0, index=range(5, 0, -1), columns=range(1, 6))
        for a_ in AMEACAS:
            grade.loc[a_.i_res, a_.p_res] += 1
        fig = px.imshow(grade.values, x=[f"P{p}" for p in grade.columns], y=[f"I{i}" for i in grade.index],
                        text_auto=True, color_continuous_scale=SEQ_VERDE,
                        title="STRIDE residual: ameaças por Probabilidade × Impacto",
                        labels=dict(color="ameaças"))
        fig.update_traces(xgap=2, ygap=2)
        fig.update_coloraxes(showscale=False)
        st.plotly_chart(layout(fig, 360), use_container_width=True)

    mit = pd.DataFrame(sast.get("mitigados", []))
    if len(mit):
        st.subheader("O que foi corrigido")
        tabela_mit = mit[["ferramenta", "regra", "severidade", "arquivo", "risco", "correcao"]].rename(columns={
            "ferramenta": "Ferramenta", "regra": "Regra", "severidade": "Severidade", "arquivo": "Onde",
            "risco": "Risco", "correcao": "Correção"})
        st.table(tabela_mit.set_index("Ferramenta"))  # st.table quebra a linha; st.dataframe cortava o texto

    obs = dados.relatorio("observabilidade_demo.json") or {}
    guard = (dados.relatorio("avaliacao_nlp.json") or {}).get("guardrail", {}).get("v2", {})
    a, b = st.columns(2)
    with a:
        st.subheader("Observabilidade (anomalias injetadas)")
        inj = pd.DataFrame(obs.get("anomalias_injetadas", []))
        if len(inj):
            inj["detectado"] = inj["detectado"].map({True: "detectada", False: "não detectada"})
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
        st.caption("Gráficos dinâmicos e pulsação da rede: lotes cadastrados pela API pública ao vivo (atualização automática a cada 20 s).")
        r = dados.recentes()
        if r.empty:
            st.info("Nenhum lote ao vivo ainda. Cadastre um pelo Swagger da API: "
                    f"{dados.API_PUBLICA}/docs")
        else:
            tabela, niveis, n_critica, n_alta = dados.alertas_ao_vivo(r)
            c = st.columns(4)
            c[0].metric("Lotes ao vivo", len(r))
            c[1].metric("kg cadastrados", br(r["peso_kg"].sum(), 1))
            c[2].metric("Entregues", int((r["status_final"] == "ENTREGUE").sum()))
            c[3].metric("Alertas pendentes", n_critica + n_alta)
            if n_critica:
                st.error(f"{n_critica} lote(s) CRÍTICO(S) pendente(s): validade curta, ofertados primeiro às ONGs.")
            if n_alta:
                st.warning(f"{n_alta} lote(s) de prioridade ALTA pendente(s).")
            fundo = {"critico": "background-color: #f8d4d4; color: #5c1010",
                     "atencao": "background-color: #fdedc4; color: #4d3500"}
            formatos = {"peso_kg": "{:.1f}", "risco_descarte": "{:.2f}"}  # o Styler usa 6 casas por padrão
            estilo = tabela.style.apply(lambda _: [fundo.get(niveis[i], "") for i in range(len(tabela))], axis=0) \
                .format({c: f for c, f in formatos.items() if c in tabela}, na_rep="—")
            st.dataframe(estilo, hide_index=True, use_container_width=True)
            st.markdown(" ".join(selo_prioridade(p) for p in COR_PRIORIDADE), unsafe_allow_html=True)
            st.caption("Linha vermelha: CRÍTICA pendente · linha amarela: ALTA pendente · a prioridade vem do Modelo 1 "
                       "com piso de segurança, que já considera a validade calculada pelo sistema.")

    ao_vivo()

st.caption("Código: github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE · Projeto Integrador FIAP 2026 · Prof. Oerton Fernandes")

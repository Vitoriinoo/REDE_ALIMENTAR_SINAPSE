"""Tela da ONG: ofertas da vez (oferta sequencial, regras 6.2), aceite/recusa, confirmação da entrega e histórico.

A ONG vê o alimento e a logística, nunca quem doou (minimização, regras 11).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import escape

import pandas as pd
import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar
from src.dashboard.dados import PRIORIDADE
from src.dashboard.tema import MUDO, STATUS, TINTA_2, VERDE, aplicar_tema, cabecalho, cartao, selo_prioridade

BRASILIA = timezone(timedelta(hours=-3))
aplicar_tema()
ident, chave = st.session_state.get("ident") or {}, st.session_state.get("chave")
if ident.get("papel") != "ong":
    st.warning("Entre com uma conta de ONG para ver esta tela.")
    st.stop()

CATEGORIA = {"preparado": "Preparado", "refrigerado": "Refrigerado", "congelado": "Congelado",
             "hortifruti": "Hortifrúti", "padaria": "Padaria", "nao_perecivel": "Não perecível"}
ARMAZENAMENTO = {"refrigerado": "na geladeira", "congelado": "no freezer", "ambiente": "em temperatura ambiente"}

cabecalho(f"Olá, {ident.get('nome') or ident['id']}",
          "Aqui chegam os alimentos oferecidos para a sua ONG. Aceite, receba e confirme: cada passo leva um clique. "
          "As ofertas atualizam sozinhas a cada 15 s.")
if aviso := st.session_state.pop("aviso_ong", None):
    (st.success if aviso[0] == "ok" else st.error)(aviso[1])
aba_ofertas, aba_historico, aba_perfil = st.tabs(["Ofertas e entregas", "Histórico de recebimentos", "Meu cadastro"])


def _hora(valor) -> str:
    return datetime.fromisoformat(str(valor)).astimezone(BRASILIA).strftime("%d/%m %H:%M") if valor else "—"


def _horas_restantes(valor) -> str:
    """Texto colorido com o tempo até a validade efetiva calculada pela API (sem limite novo de horas)."""
    if not valor:
        return ""
    resta = datetime.fromisoformat(str(valor)) - datetime.now(timezone.utc)
    horas = resta.total_seconds() / 3600
    if horas <= 0:
        return f"<span style='color:{STATUS['critico']};font-weight:600'>validade vencida</span>"
    texto = f"{horas:.0f} h" if horas >= 1 else f"{resta.total_seconds() / 60:.0f} min"
    cor = STATUS["critico"] if horas < 6 else STATUS["atencao"] if horas < 24 else VERDE
    return f"<span style='color:{cor};font-weight:600'>restam {texto}</span> · vence {_hora(valor)}"


def link_google_maps(item: dict) -> str | None:
    """Link de rota quando a API mandar origem e destino com coordenadas (PLANO-TELAS, decisão 9)."""
    try:
        o = f"{float(item['origem_lat'])},{float(item['origem_lon'])}"
        d = f"{float(item['destino_lat'])},{float(item['destino_lon'])}"
    except (KeyError, TypeError, ValueError):
        return None
    return f"https://www.google.com/maps/dir/?api=1&origin={o}&destination={d}&travelmode=driving"


def _corpo(o: dict, extra: str = "") -> str:
    logistica = "direto do doador" if o.get("modo") == "direto" else "via hub (ponto de encontro)"
    km = f"{o['km']:.1f} km" if o.get("km") is not None else "distância indisponível"
    minutos = f" · chega em ~{o['minutos_ate_receber']:.0f} min" if o.get("minutos_ate_receber") is not None else ""
    return (f"<div style='margin:.35rem 0'>{selo_prioridade(o.get('prioridade') or '')} &nbsp;"
            f"{_horas_restantes(o.get('validade_efetiva'))}</div>"
            f"<div style='color:{TINTA_2}'>{km}{minutos} · {logistica}<br>"
            f"~{o['refeicoes_estimadas']:.0f} refeições · guardado "
            f"{escape(ARMAZENAMENTO.get(o.get('armazenamento'), o.get('armazenamento') or ''))}{extra}</div>")


def _titulo(o: dict) -> str:
    return f"{CATEGORIA.get(o['categoria'], o['categoria'])} · {o['peso_kg']:.1f} kg".replace(".", ",")


def _agir(rota: str, corpo: dict | None, sucesso: str) -> None:
    """A mensagem vai para a sessão: o st.rerun() logo depois apagaria um toast."""
    try:
        r = chamar("POST", rota, chave, corpo)
        st.session_state["aviso_ong"] = ("ok", sucesso.format(**r))
    except ErroAPI as e:
        st.session_state["aviso_ong"] = ("erro", e.mensagem)


@st.fragment(run_every="15s")
def painel_ong() -> None:
    try:
        dados = chamar("GET", "/v1/ong/ofertas", chave)
    except ErroAPI as e:
        st.error(e.mensagem)
        return

    st.markdown(f"<p style='color:{MUDO}'><b>Como funciona:</b> 1. Aceite ou recuse a oferta &nbsp;→&nbsp; "
                "2. Receba o alimento e faça a inspeção &nbsp;→&nbsp; 3. Confirme a entrega.</p>",
                unsafe_allow_html=True)

    st.subheader(f"1. Ofertas para você ({len(dados['ofertas'])})")
    if not dados["ofertas"]:
        st.info("Nenhuma oferta aguardando sua resposta agora. Assim que um doador próximo cadastrar um lote "
                "compatível, ele aparece aqui.")
    else:
        st.caption("A oferta é só sua até você responder. Se recusar, ela passa para a próxima ONG da fila.")
    for o in dados["ofertas"]:
        esq, dir_ = st.columns([3, 1], vertical_alignment="center")
        with esq:
            cartao(_titulo(o), _corpo(o), sub=f"Lote {o['codigo']} · doador em {o['regiao_doador']}")
        with dir_:
            if st.button("Aceitar", key=f"ac_{o['codigo']}", type="primary", width="stretch"):
                _agir(f"/v1/lotes/{o['codigo']}/aceite", None, "Aceito em {minutos_ate_match} min do cadastro.")
                st.rerun()
            if st.button("Recusar", key=f"rc_{o['codigo']}", width="stretch"):
                _agir(f"/v1/lotes/{o['codigo']}/recusa", None, "Recusado: oferta passou para {proxima_ong}.")
                st.rerun()
            if url := link_google_maps(o):
                st.link_button("Abrir no Google Maps", url, width="stretch")

    st.subheader(f"2. Aguardando entrega ({len(dados['aguardando_entrega'])})")
    if not dados["aguardando_entrega"]:
        st.info("Nenhum lote a caminho.")
    else:
        st.caption("Na chegada, confira cheiro, temperatura, embalagem e validade (regras 6.2.1) e confirme.")
    for o in dados["aguardando_entrega"]:
        esq, dir_ = st.columns([3, 2], vertical_alignment="center")
        with esq:
            cartao(_titulo(o), _corpo(o, f"<br>aceito em {_hora(o.get('ts_aceite_ong'))}"), sub=f"Lote {o['codigo']}")
        with dir_:
            aprovada = st.radio("Inspeção na chegada", ["Aprovada", "Reprovada"], key=f"in_{o['codigo']}",
                                horizontal=True, help="Cheiro, temperatura, embalagem, validade (regras 6.2.1)")
            if st.button("Confirmar entrega", key=f"en_{o['codigo']}", type="primary", width="stretch"):
                _agir(f"/v1/lotes/{o['codigo']}/entrega", {"inspecao_aprovada": aprovada == "Aprovada"},
                      "Entrega registrada: {status} · {refeicoes} refeições.")
                st.rerun()
            if url := link_google_maps(o):
                st.link_button("Abrir no Google Maps", url, width="stretch")


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
    }), hide_index=True, width="stretch")
    st.caption("A ONG vê o alimento e o resultado, nunca quem doou (minimização, LGPD).")


IPVS = {1: "baixíssima", 2: "muito baixa", 3: "baixa", 4: "média", 5: "alta", 6: "muito alta", 7: "alta (rural)"}
TURNOS = {"cafe": "café", "almoco": "almoço", "jantar": "jantar", "noturno": "noturno"}


def _sim(valor: bool) -> str:
    return "Sim" if valor else "Não"


def meu_cadastro() -> None:
    try:
        p = chamar("GET", "/v1/ong/perfil", chave)
    except ErroAPI as e:
        st.error(e.mensagem)
        return
    st.caption("Cadastro aprovado pela administração depois da validação do CNPJ (dígito verificador + Receita). "
               "É com estes dados que o sistema decide o que oferecer a esta ONG.")
    c = st.columns(3)
    c[0].metric("Região", p["regiao"])
    c[1].metric("Vulnerabilidade do setor (IPVS)", f"grupo {p['ipvs_grupo']}")
    c[1].caption(f"{IPVS.get(p['ipvs_grupo'], '')} · pesa 30% no ranking: quanto mais vulnerável, mais prioridade")
    c[2].metric("Capacidade", f"{p['capacidade_kg_dia']:.0f} kg/dia")

    esq, dir_ = st.columns(2)
    with esq:
        if p["aceita_receber_entrega"] and p["pode_buscar"]:
            logistica = "Busca e também recebe entrega"
        elif p["pode_buscar"]:
            logistica = "Só busca (não recebe entrega)"
        else:
            logistica = "Só recebe entrega (sem veículo)"
        itens = [("Cozinha", _sim(p["tem_cozinha"])), ("Geladeira", _sim(p["tem_refrigeracao"])),
                 ("Freezer", _sim(p["tem_freezer"])), ("Distribui cestas", _sim(p["distribui_cestas"])),
                 ("Serve refeição", _sim(p["serve_refeicao"])), ("Logística", logistica),
                 ("Horário de recebimento", f"{p['abertura_h']:.0f}h às {p['fechamento_h']:.0f}h"),
                 ("Turnos", ", ".join(TURNOS.get(x, x) for x in p["turnos"]) or "—"),
                 ("Aceita", ", ".join(CATEGORIA.get(x, x) for x in p["categorias_aceitas"]))]
        linhas = "".join(f"<tr><td style='color:{MUDO};padding:.15rem 1rem .15rem 0'>{escape(k)}</td>"
                         f"<td><b>{escape(v)}</b></td></tr>" for k, v in itens)
        cartao("Estrutura cadastrada", f"<table style='margin-top:.4rem'>{linhas}</table>")
    with dir_:
        st.map(pd.DataFrame({"lat": [p["lat"]], "lon": [p["lon"]]}), zoom=11, height=260)
        st.caption(f"{p['municipio']} · posição aproximada (3 casas decimais)")

    st.markdown("**Como o sistema usa este cadastro**")
    st.markdown("\n".join([
        "- **Filtro (regra rígida):** só oferece categoria que a ONG aceita e que a estrutura comporta "
        "(refrigerado exige geladeira, congelado exige freezer, preparar exige cozinha ou cestas).",
        "- **Logística:** \"só busca\" com doador que \"só entrega\" é bloqueado; a saída é o hub como ponto de "
        "encontro.",
        "- **Ranking:** tempo até receber (inclui o horário acima), capacidade, vulnerabilidade do setor e "
        "pedidos abertos.",
        "- **Alteração:** passa pela administração, com nova validação (evita ONG declarar estrutura que não tem).",
    ]))


with aba_ofertas:
    painel_ong()
with aba_historico:
    historico()
with aba_perfil:
    meu_cadastro()

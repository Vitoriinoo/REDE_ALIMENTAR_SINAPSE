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
if aviso := st.session_state.pop("aviso_ong", None):
    (st.success if aviso[0] == "ok" else st.error)(aviso[1])
aba_ofertas, aba_historico, aba_perfil = st.tabs(["Ofertas e entregas", "Histórico de recebimentos", "Meu cadastro"])


def _hora(valor) -> str:
    return datetime.fromisoformat(str(valor)).astimezone(BRASILIA).strftime("%d/%m %H:%M") if valor else "—"


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
                st.rerun()
            if c[3].button("Recusar", key=f"rc_{o['codigo']}", use_container_width=True):
                _agir(f"/v1/lotes/{o['codigo']}/recusa", None, "Recusado: oferta passou para {proxima_ong}.")
                st.rerun()

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
                st.rerun()


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
        st.table(pd.DataFrame({"Item": [
            "Cozinha", "Geladeira", "Freezer", "Distribui cestas", "Serve refeição", "Logística",
            "Horário de recebimento", "Turnos"], "Cadastro": [
            _sim(p["tem_cozinha"]), _sim(p["tem_refrigeracao"]), _sim(p["tem_freezer"]), _sim(p["distribui_cestas"]),
            _sim(p["serve_refeicao"]), logistica, f"{p['abertura_h']:.0f}h às {p['fechamento_h']:.0f}h",
            ", ".join(TURNOS.get(x, x) for x in p["turnos"]) or "—"]}).set_index("Item"))
        st.markdown("**Aceita:** " + ", ".join(CATEGORIA.get(x, x) for x in p["categorias_aceitas"]))
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

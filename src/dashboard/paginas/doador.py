"""Tela do doador: descreve o lote, a IA sugere, o doador confirma, responde o questionário e doa.

Categorias, perguntas aplicáveis e o texto da declaração vêm de `src/regras` (a mesma fonte da
API). A decisão (aceite, prioridade, ONG) é sempre da API: esta tela só coleta e mostra.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

import pandas as pd
import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar, traduzir
from src.regras.dominio import Armazenamento, Categoria, TipoDoador
from src.regras.questionario import PERGUNTAS, TEXTO_DECLARACAO, Alergenico, Origem, perguntas_aplicaveis

BRASILIA = timezone(timedelta(hours=-3))
ident, chave = st.session_state.get("ident") or {}, st.session_state.get("chave")
if ident.get("papel") != "doador":
    st.warning("Entre com uma chave de doador na barra lateral.")
    st.stop()

CATEGORIAS = {Categoria.PREPARADO: "Preparado (refeição pronta)", Categoria.REFRIGERADO: "Refrigerado",
              Categoria.CONGELADO: "Congelado", Categoria.HORTIFRUTI: "Hortifrúti", Categoria.PADARIA: "Padaria",
              Categoria.NAO_PERECIVEL: "Não perecível"}
ARMAZENAMENTOS = {Armazenamento.REFRIGERADO: "Na geladeira", Armazenamento.CONGELADO: "No freezer",
                  Armazenamento.AMBIENTE: "Fora da geladeira (ambiente)"}
OPCOES_ARM = {Categoria.PREPARADO: [Armazenamento.REFRIGERADO, Armazenamento.AMBIENTE],
              Categoria.REFRIGERADO: [Armazenamento.REFRIGERADO, Armazenamento.AMBIENTE],
              Categoria.CONGELADO: [Armazenamento.CONGELADO, Armazenamento.AMBIENTE]}
ORIGENS = {Origem.EXCEDENTE_PRODUCAO: "Sobra da produção do dia", Origem.EXCEDENTE_ESTOQUE: "Excedente de estoque",
           Origem.SOBRA_EVENTO: "Sobra de evento", Origem.OUTRO: "Outro"}
ALERGENICOS = {a: a.value.replace("_", " ").capitalize() for a in Alergenico}
ALERGENICOS[Alergenico.NAO_SEI] = "Não sei"
VALIDADE_PADRAO_DIAS = {Categoria.REFRIGERADO: 3, Categoria.CONGELADO: 60, Categoria.HORTIFRUTI: 4,
                        Categoria.PADARIA: 2, Categoria.NAO_PERECIVEL: 180}
EXCLUSOES = {"fora_do_raio": "fora do raio de 20 km", "categoria_nao_aceita": "não aceitam esta categoria",
             "sem_refrigeracao": "sem geladeira", "sem_freezer": "sem freezer", "sem_cozinha": "sem cozinha",
             "impasse_busca_entrega": "impasse 'só busca × só entrega'", "sem_capacidade": "sem capacidade hoje",
             "nao_chega_a_tempo": "não recebem antes de vencer", "doador_indisponivel": "fora da sua janela",
             "rota_expressa": "fora da rota expressa"}
FONTES = {"modelo": "Modelo 1 (IA)", "regra": "regra (IA desligada ou indisponível)",
          "piso_de_seguranca": "piso de segurança (a regra disse CRÍTICA)"}


def instante(dia: date, hora: time) -> str:
    return datetime.combine(dia, hora, tzinfo=BRASILIA).isoformat()


def agora() -> datetime:
    return datetime.now(BRASILIA).replace(second=0, microsecond=0)


tipo = TipoDoador(ident.get("tipo_doador", "PJ"))
st.title("Doar alimentos")
st.caption(f"Doador `{ident['id']}` · {'pessoa jurídica' if tipo == TipoDoador.PJ else 'pessoa física'} · "
           f"{ident.get('segmento', '')} · {ident.get('regiao', '')}")
if tipo == TipoDoador.PF:
    st.info("Pessoa física pode doar apenas **alimento não perecível lacrado** na embalagem original (regras 4.1).")

aba_doar, aba_meus = st.tabs(["Nova doação", "Minhas doações"])

with aba_doar:
    # --- 1. Descrição + sugestão da IA ------------------------------------------------------
    st.subheader("1. O que você quer doar?")
    descricao = st.text_area("Descreva o lote com suas palavras", max_chars=500, key="descricao",
                             placeholder="Ex.: sobraram 20 marmitas de arroz, feijão e frango do almoço, estão na geladeira")
    if st.button("Pedir sugestão da IA", disabled=len(descricao.strip()) < 3):
        try:
            st.session_state["sugestao"] = chamar("POST", "/v1/lotes/sugestao", chave, {"texto": descricao.strip()})
        except ErroAPI as e:
            st.error(e.mensagem)
    sug = st.session_state.get("sugestao")
    if sug and sug.get("sugestao"):
        s = sug["sugestao"]
        st.success(f"A IA sugere **{CATEGORIAS[Categoria(s['categoria'])]}** · "
                   f"{ARMAZENAMENTOS[Armazenamento(s['armazenamento'])].lower()} "
                   f"(confiança {sug['confianca']:.0%}). **Confira e confirme abaixo:** a decisão é sua.")
    elif sug:
        st.info(sug.get("mensagem", "Sem sugestão automática: escolha a categoria."))

    # --- 2. Confirmação da categoria e da validade -------------------------------------------
    st.subheader("2. Confirme o alimento")
    lista_cat = list(CATEGORIAS)
    sugerida = Categoria(sug["sugestao"]["categoria"]) if sug and sug.get("sugestao") else None
    c1, c2, c3 = st.columns(3)
    categoria = c1.selectbox("Categoria", lista_cat, format_func=CATEGORIAS.get,
                             index=lista_cat.index(sugerida) if sugerida else 0)
    opcoes_arm = OPCOES_ARM.get(categoria, [Armazenamento.AMBIENTE, Armazenamento.REFRIGERADO])
    arm_sugerido = Armazenamento(sug["sugestao"]["armazenamento"]) if sug and sug.get("sugestao") else None
    armazenamento = c2.selectbox("Onde está agora", opcoes_arm, format_func=ARMAZENAMENTOS.get,
                                 index=opcoes_arm.index(arm_sugerido) if arm_sugerido in opcoes_arm else 0)
    peso = c3.number_input("Peso (kg)", min_value=0.5, max_value=10_000.0, value=10.0, step=0.5)

    datas: dict[str, str] = {}
    a, b = st.columns(2)
    if categoria == Categoria.PREPARADO:
        ref = agora() - timedelta(hours=1)
        datas["preparo"] = instante(a.date_input("Dia do preparo", ref.date(), format="DD/MM/YYYY"),
                                    b.time_input("Hora do preparo", ref.time()))
        st.caption("A plataforma **calcula** a validade: fora da geladeira = preparo + 3 h; na geladeira = + 72 h.")
    elif categoria in (Categoria.REFRIGERADO, Categoria.CONGELADO):
        venc = agora() + timedelta(days=VALIDADE_PADRAO_DIAS[categoria])
        datas["validade_rotulo"] = instante(a.date_input("Validade no rótulo", venc.date(), format="DD/MM/YYYY"),
                                            time(23, 59))
        if armazenamento == Armazenamento.AMBIENTE:
            saida = agora() - timedelta(minutes=30)
            datas["saida_refrigeracao"] = instante(saida.date(), b.time_input("Saiu da refrigeração às", saida.time()))
            st.caption("Fora da refrigeração, vale o menor entre o rótulo e saída + 3 h (rota expressa).")
    else:
        venc = agora() + timedelta(days=VALIDADE_PADRAO_DIAS[categoria])
        datas["validade_informada"] = instante(a.date_input("Validade", venc.date(), format="DD/MM/YYYY"), time(23, 59))

    # --- 3. Questionário (só as perguntas que valem para esta categoria e este doador) -------
    st.subheader("3. Questionário de segurança do alimento")
    aplicaveis = perguntas_aplicaveis(categoria, tipo)
    sim_nao = {"Sim": True, "Não": False}
    r: dict = {}
    r["origem"] = st.selectbox(f"Q1. {PERGUNTAS['Q1']}", list(ORIGENS), format_func=ORIGENS.get)
    r["embalagem_integra"] = sim_nao[st.radio(f"Q2. {PERGUNTAS['Q2']}", list(sim_nao), horizontal=True)]
    r["alergenicos"] = st.multiselect(f"Q3. {PERGUNTAS['Q3']}", list(ALERGENICOS), default=[Alergenico.NENHUM],
                                      format_func=ALERGENICOS.get)
    r["requer_preparo"] = sim_nao[st.radio(f"Q4. {PERGUNTAS['Q4']}", list(sim_nao), index=1, horizontal=True)]
    condicionais = {"Q6": "exposto_consumidor", "Q7": "rotulo_visivel", "Q8": "descongelado",
                    "Q9": "lacrado_original", "Q10": "selecionado"}
    faltando = []
    for pid, campo in condicionais.items():
        if pid in aplicaveis:
            escolha = st.radio(f"{pid}. {PERGUNTAS[pid]}", list(sim_nao), index=None, horizontal=True, key=f"q_{pid}")
            if escolha is None:
                faltando.append(pid)
            else:
                r[campo] = sim_nao[escolha]
    r["declaracao_condicoes"] = st.checkbox(f"Q5. {TEXTO_DECLARACAO}")

    disponivel = st.checkbox("O lote só pode sair até um horário (ex.: o estabelecimento fecha)")
    if disponivel:
        ate = agora() + timedelta(hours=3)
        x, y = st.columns(2)
        datas["disponivel_ate"] = instante(x.date_input("Disponível até (dia)", ate.date(), format="DD/MM/YYYY"),
                                           y.time_input("Disponível até (hora)", ate.time()))

    if st.button("Cadastrar doação", type="primary", use_container_width=True):
        if len(descricao.strip()) < 3:
            st.error("Descreva o lote no passo 1.")
        elif faltando:
            st.error(f"Responda as perguntas {', '.join(faltando)}.")
        else:
            corpo = {"descricao": descricao.strip(), "categoria": categoria.value,
                     "armazenamento": armazenamento.value, "peso_kg": float(peso), **datas,
                     "questionario": {**{k: (v.value if hasattr(v, "value") else v) for k, v in r.items()
                                         if k != "alergenicos"},
                                      "alergenicos": [a.value for a in r["alergenicos"]]}}
            try:
                with st.spinner("Validando, calculando prioridade e procurando ONG..."):
                    st.session_state["resultado"] = chamar("POST", "/v1/lotes", chave, corpo)
            except ErroAPI as e:
                st.session_state.pop("resultado", None)
                st.error(f"Não foi possível cadastrar: {e.mensagem}")

    # --- 4. Resultado -------------------------------------------------------------------------
    res = st.session_state.get("resultado")
    if res:
        st.divider()
        st.subheader("Resultado")
        validade = datetime.fromisoformat(res["validade_efetiva"]).astimezone(BRASILIA)
        if res["resultado"] == "BLOQUEADO":
            st.error("**Doação não aceita.** " + " ".join(traduzir(m) for m in res["motivos"]))
            if res.get("orientacao"):
                st.caption(res["orientacao"])
        elif res["resultado"] == "SEM_ONG_ELEGIVEL":
            st.warning(traduzir("SEM_ONG_ELEGIVEL") + " O lote foi registrado e a tentativa fica na sua declaração.")
        else:
            ong = res["ong_ofertada"]
            st.success(f"**Doação aceita!** Ofertada à ONG **{ong['ong_id']}** ({ong['regiao']}).")
            m = st.columns(4)
            p = res["prioridade"]
            m[0].metric("Prioridade", p["valor"].replace("CRITICA", "CRÍTICA").replace("MEDIA", "MÉDIA"))
            m[0].caption(f"decidida por: {FONTES.get(p['fonte'], p['fonte'])}")
            rd = res["risco_descarte"]
            m[1].metric("Risco de descarte", "ALTO" if rd["alto"] else "normal",
                        f"{rd['probabilidade']:.0%}" if rd.get("probabilidade") is not None else None, delta_color="off")
            m[1].caption("Modelo 2: se alto, libera o entregador pago (caixa solidário)")
            m[2].metric("Refeições estimadas", f"{res['refeicoes_estimadas']:.0f}")
            m[3].metric("Validade calculada", validade.strftime("%d/%m %H:%M"))
            st.markdown(f"**ONG da vez:** `{ong['ong_id']}` · {ong['km']:.1f} km · pode receber em "
                        f"~{ong['minutos_ate_receber']:.0f} min · logística: "
                        f"{'direta' if ong['modo'] == 'direto' else 'via hub (ponto de encontro)'}")
            if res.get("alternativas"):
                st.caption("Se ela recusar, a oferta passa para a próxima, nesta ordem:")
                st.dataframe(pd.DataFrame(res["alternativas"])[["ong_id", "regiao", "score", "km",
                                                                "minutos_ate_receber", "modo"]],
                             hide_index=True, use_container_width=True)
            if res.get("ongs_excluidas"):
                with st.expander("Por que as outras ONGs ficaram de fora"):
                    for motivo, n in sorted(res["ongs_excluidas"].items(), key=lambda x: -x[1]):
                        st.write(f"- **{n}** ONG(s): {EXCLUSOES.get(motivo, motivo)}")
        d = res["declaracao"]
        with st.container(border=True):
            st.markdown(f"**Declaração de Doação** `{d['id']}`  \nAssinada com {d['assinatura']} · "
                        f"SHA-256 `{d['sha256'][:24]}…` · registrada no banco (só inclusão).")
            try:
                pdf = chamar("GET", f"/v1/lotes/{res['codigo']}/declaracao.pdf", chave, bruto=True)
                st.download_button("Baixar declaração (PDF)", pdf, file_name=f"declaracao-{res['codigo']}.pdf",
                                   mime="application/pdf")
            except ErroAPI as e:
                st.caption(f"PDF indisponível: {e.mensagem}")

with aba_meus:
    try:
        lotes = pd.DataFrame(chamar("GET", "/v1/doador/lotes", chave))
    except ErroAPI as e:
        st.error(e.mensagem)
        lotes = pd.DataFrame()
    if lotes.empty:
        st.info("Você ainda não cadastrou doações.")
    else:
        lotes["ts_cadastro"] = pd.to_datetime(lotes["ts_cadastro"], utc=True).dt.tz_convert(BRASILIA).dt.strftime(
            "%d/%m %H:%M")
        st.dataframe(lotes.rename(columns={"codigo": "lote", "ts_cadastro": "cadastro", "ong_codigo": "ONG",
                                           "status_final": "situação"}), hide_index=True, use_container_width=True)

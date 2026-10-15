"""Tela do doador: descreve o lote, a IA sugere, o doador confirma, responde o questionário e doa.

Categorias, perguntas aplicáveis e o texto da declaração vêm de `src/regras` (a mesma fonte da
API). A decisão (aceite, prioridade, ONG) é sempre da API: esta tela só coleta e mostra.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from html import escape

import pandas as pd
import streamlit as st

from src.dashboard.cliente_api import ErroAPI, chamar, traduzir
from src.dashboard.tema import MUDO, STATUS, TINTA_2, VERDE, aplicar_tema, cabecalho, cartao, selo_prioridade
from src.regras.dominio import Armazenamento, Categoria, TipoDoador
from src.regras.questionario import PERGUNTAS, TEXTO_DECLARACAO, Alergenico, Origem, perguntas_aplicaveis

BRASILIA = timezone(timedelta(hours=-3))
aplicar_tema()
ident, chave = st.session_state.get("ident") or {}, st.session_state.get("chave")
if ident.get("papel") != "doador":
    st.warning("Entre com uma conta de doador para ver esta tela.")
    st.stop()
if "tipo_doador" not in ident:  # o login por e-mail traz só papel, id e nome; o resto vem de /v1/eu
    try:
        ident = st.session_state["ident"] = ident | chamar("GET", "/v1/eu", chave)
    except ErroAPI:
        pass

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


def horas_restantes(validade: datetime) -> str:
    """Tempo até a validade efetiva calculada pela API, colorido (sem limite novo de horas)."""
    resta = validade - datetime.now(BRASILIA)
    horas = resta.total_seconds() / 3600
    if horas <= 0:
        return f"<span style='color:{STATUS['critico']};font-weight:600'>validade vencida</span>"
    texto = f"{horas:.0f} h" if horas >= 1 else f"{resta.total_seconds() / 60:.0f} min"
    cor = STATUS["critico"] if horas < 6 else STATUS["atencao"] if horas < 24 else VERDE
    return f"<span style='color:{cor};font-weight:600'>restam {texto}</span> · vence {validade:%d/%m %H:%M}"


def link_google_maps(item: dict) -> str | None:
    """Link de rota quando a API mandar origem e destino com coordenadas (PLANO-TELAS, decisão 9)."""
    try:
        o = f"{float(item['origem_lat'])},{float(item['origem_lon'])}"
        d = f"{float(item['destino_lat'])},{float(item['destino_lon'])}"
    except (KeyError, TypeError, ValueError):
        return None
    return f"https://www.google.com/maps/dir/?api=1&origin={o}&destination={d}&travelmode=driving"


def passo(numero: int, titulo: str, ajuda: str) -> None:
    st.markdown(f"<div style='margin:1.2rem 0 .3rem'><span class='ra-selo' style='background:{VERDE}'>"
                f"Passo {numero}</span> <b style='font-size:1.15rem'>{escape(titulo)}</b>"
                f"<div style='color:{MUDO};font-size:.9rem'>{escape(ajuda)}</div></div>", unsafe_allow_html=True)


tipo = TipoDoador(ident.get("tipo_doador", "PJ"))
detalhes = " · ".join(x for x in ("pessoa jurídica" if tipo == TipoDoador.PJ else "pessoa física",
                                  ident.get("segmento"), ident.get("regiao")) if x)
cabecalho(f"Olá, {ident.get('nome') or ident['id']}",
          f"Obrigado por doar. Em quatro passos o seu alimento chega a uma ONG perto de você. ({detalhes})")
if tipo == TipoDoador.PF:
    st.info("Pessoa física pode doar apenas **alimento não perecível lacrado** na embalagem original (regras 4.1).")

aba_doar, aba_meus = st.tabs(["Nova doação", "Minhas doações"])

with aba_doar:
    # --- 1. Descrição + sugestão da IA ------------------------------------------------------
    passo(1, "O que você quer doar?", "Conte com suas palavras; a IA sugere a categoria e você confere.")
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
    passo(2, "Confirme o alimento", "Categoria, onde está guardado, peso e validade.")
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
    passo(3, "Segurança do alimento", "Só as perguntas que valem para este alimento. Leva menos de um minuto.")
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

    passo(4, "Enviar", "A plataforma valida, calcula a prioridade e oferece o lote à ONG mais adequada.")
    if st.button("Cadastrar doação", type="primary", width="stretch"):
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
            p = res["prioridade"]
            rd = res["risco_descarte"]
            prob = f" ({rd['probabilidade']:.0%})" if rd.get("probabilidade") is not None else ""
            cartao(f"Lote {res['codigo']}",
                   f"<div style='margin:.35rem 0'>{selo_prioridade(p['valor'])} &nbsp;{horas_restantes(validade)}</div>"
                   f"<div style='color:{TINTA_2}'>Prioridade decidida por: {escape(FONTES.get(p['fonte'], p['fonte']))}"
                   f"<br>~{res['refeicoes_estimadas']:.0f} refeições estimadas · risco de descarte "
                   f"<b>{'ALTO' if rd['alto'] else 'normal'}</b>{prob}</div>",
                   sub="Modelo 2: risco alto libera o entregador pago (caixa solidário)")
            logistica = "direta" if ong["modo"] == "direto" else "via hub (ponto de encontro)"
            esq, dir_ = st.columns([3, 1], vertical_alignment="center")
            with esq:
                cartao(f"ONG da vez: {ong['ong_id']}",
                       f"<div style='color:{TINTA_2}'>{ong['km']:.1f} km · pode receber em "
                       f"~{ong['minutos_ate_receber']:.0f} min · logística {logistica}</div>",
                       sub=f"{ong['regiao']} · ela tem a vez de aceitar ou recusar")
            with dir_:
                if url := link_google_maps(ong):
                    st.link_button("Abrir no Google Maps", url, width="stretch")
            if res.get("alternativas"):
                st.caption("Se ela recusar, a oferta passa para a próxima, nesta ordem:")
                st.dataframe(pd.DataFrame(res["alternativas"])[["ong_id", "regiao", "score", "km",
                                                                "minutos_ate_receber", "modo"]],
                             hide_index=True, width="stretch")
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
        st.info("Você ainda não cadastrou doações. Comece pela aba Nova doação.")
    else:
        entregues = lotes[lotes["status_final"] == "ENTREGUE"]
        c = st.columns(3)
        c[0].metric("Doações", len(lotes))
        c[1].metric("Entregues", len(entregues))
        c[2].metric("Refeições", f"{pd.to_numeric(entregues['refeicoes'], errors='coerce').fillna(0).sum():.0f}")
        lotes["ts_cadastro"] = pd.to_datetime(lotes["ts_cadastro"], utc=True).dt.tz_convert(BRASILIA).dt.strftime(
            "%d/%m %H:%M")
        lotes["prioridade"] = lotes["prioridade"].map(
            lambda v: {"CRITICA": "CRÍTICA", "MEDIA": "MÉDIA"}.get(v, v))
        st.dataframe(lotes.rename(columns={"codigo": "lote", "ts_cadastro": "cadastro", "ong_codigo": "ONG",
                                           "status_final": "situação"}), hide_index=True, width="stretch")

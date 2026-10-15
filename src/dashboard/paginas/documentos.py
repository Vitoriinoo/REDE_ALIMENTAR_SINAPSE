"""Documentos assinados: ver a Declaração de Doação e verificar a assinatura (regras 4.5).

Duas verificações: a da API (item a item) e uma INDEPENDENTE, feita aqui com a chave pública,
sem confiar na resposta da API. "Simular adulteração" altera uma cópia local e mostra a
assinatura deixando de conferir. Doador vê só os próprios documentos; admin vê os recentes.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from src.dashboard.cliente_api import ErroAPI, chamar
from src.seguranca.declaracao import DeclaracaoAssinada, verificar_itens

BRASILIA = timezone(timedelta(hours=-3))
ident, chave = st.session_state.get("ident") or {}, st.session_state.get("chave")
if ident.get("papel") not in ("doador", "admin"):
    st.warning("Entre com uma chave de doador ou de administração.")
    st.stop()

CATEGORIA = {"preparado": "Preparado", "refrigerado": "Refrigerado", "congelado": "Congelado",
             "hortifruti": "Hortifrúti", "padaria": "Padaria", "nao_perecivel": "Não perecível"}
ARMAZENAMENTO = {"refrigerado": "Na geladeira", "congelado": "No freezer", "ambiente": "Fora da geladeira"}
# Mesmos rótulos da tela do doador (o documento guarda o código; aqui só a leitura muda).
ROTULOS = {"excedente_producao": "Sobra da produção do dia", "excedente_estoque": "Excedente de estoque",
           "sobra_evento": "Sobra de evento", "outro": "Outro", "nao_sei": "Não sei"}


def _hora(valor) -> str:
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00")).astimezone(BRASILIA).strftime(
        "%d/%m/%Y %H:%M") if valor else "—"


def _resposta(r) -> str:
    if isinstance(r, bool):
        return "Sim" if r else "Não"
    if isinstance(r, list):
        return ", ".join(_texto(x) for x in r) or "—"
    return _texto(r)


def _texto(valor) -> str:
    v = str(valor)
    return ROTULOS.get(v, v.replace("_", " ").capitalize())


def _quadro_verificacao(itens: list[dict]) -> None:
    st.table(pd.DataFrame({"Conferência": [i["item"] for i in itens],
                           "Resultado": ["Confere" if i["ok"] else "NÃO CONFERE" for i in itens],
                           "Detalhe": [i["detalhe"] for i in itens]}).set_index("Conferência"))


st.title("Documentos assinados")
st.caption("Declaração de Doação (Lei 14.016/2020): JSON canônico, SHA-256 e assinatura RSA-PSS, "
           "gravada no banco numa tabela só de inclusão.")

try:
    lotes = chamar("GET", "/v1/doador/lotes" if ident["papel"] == "doador" else "/v1/lotes", chave)
except ErroAPI as e:
    st.error(e.mensagem)
    st.stop()
if not lotes:
    st.info("Nenhum documento ainda. Cada doação cadastrada gera uma declaração assinada.")
    st.stop()

opcoes = {l["codigo"]: f"{l['codigo']} · {CATEGORIA.get(l['categoria'], l['categoria'])} · "
                       f"{float(l['peso_kg']):.1f} kg · {_hora(l['ts_cadastro'])}" for l in lotes}
codigo = st.selectbox("Doação", list(opcoes), format_func=opcoes.get)

try:
    d = chamar("GET", f"/v1/lotes/{codigo}/declaracao", chave)
    chave_publica = chamar("GET", "/v1/declaracoes/chave-publica", chave)
except ErroAPI as e:
    st.error(e.mensagem)
    st.stop()

c = d["conteudo"]
alimento, doador = c.get("alimento", {}), c.get("doador", {})

# --- O documento ----------------------------------------------------------------------------
with st.container(border=True):
    topo = st.columns(4)
    topo[0].metric("Declaração", c.get("declaracao_id", "—"))
    topo[1].metric("Versão", c.get("versao", 1))
    topo[2].metric("Resultado", {"ACEITA": "Aceita", "BLOQUEADA": "Bloqueada"}.get(c.get("resultado"),
                                                                                   c.get("resultado", "—")))
    topo[3].metric("Emitida em", _hora(c.get("emitida_em")))

    esq, dir_ = st.columns(2)
    with esq:
        st.markdown("**Alimento**")
        st.markdown(
            f"- Categoria: {CATEGORIA.get(alimento.get('categoria_confirmada'), alimento.get('categoria_confirmada'))}\n"
            f"- Armazenamento: {ARMAZENAMENTO.get(alimento.get('armazenamento_confirmado'), '—')}\n"
            f"- Peso: {alimento.get('peso_kg', '—')} kg\n"
            f"- Validade calculada pelo sistema: {_hora(alimento.get('validade_efetiva'))}\n"
            f"- Lote: `{c.get('lote_id', codigo)}`")
    with dir_:
        st.markdown("**Doador**")
        st.markdown(f"- Identificação: `{doador.get('pseudonimo', '—')}` (pseudônimo, LGPD)\n"
                    f"- Tipo: {'Pessoa jurídica' if doador.get('tipo') == 'PJ' else 'Pessoa física'}")
        if c.get("motivos_bloqueio"):
            st.markdown("**Motivos do bloqueio:** " + ", ".join(c["motivos_bloqueio"]))

    perguntas = c.get("questionario", {})
    if perguntas:
        st.markdown("**Questionário de segurança do alimento**")
        st.table(pd.DataFrame({"Pergunta": [p["pergunta"] for p in perguntas.values()],
                               "Resposta": [_resposta(p["resposta"]) for p in perguntas.values()]},
                              index=list(perguntas)))
    if c.get("texto_declaracao"):
        st.markdown(f"> {c['texto_declaracao']}")

# --- Verificação ------------------------------------------------------------------------------
st.subheader("Verificação da assinatura")
if d.get("assinatura_valida"):
    st.success("Documento íntegro: o conteúdo não foi alterado desde a assinatura da plataforma.")
else:
    st.error("Documento NÃO confere: conteúdo ou assinatura foram alterados.")
_quadro_verificacao(d["verificacao"])

publica = load_pem_public_key(chave_publica["pem"].encode())
documento = DeclaracaoAssinada.de_dict(d)
local = verificar_itens(documento, publica)
st.markdown("**Verificação independente (feita neste painel, sem confiar na API)**")
st.caption(f"Usa só a chave pública da plataforma (impressão digital `{chave_publica['chave_id']}`). "
           "Qualquer pessoa com o JSON e a chave pública repete esta conferência.")
if all(i["ok"] for i in local):
    st.success("Conferido localmente: a assinatura é válida.")
else:
    st.error("A conferência local falhou.")

with st.expander("Simular adulteração (demonstração)"):
    st.write("Altera uma cópia do documento só nesta tela (nada é gravado) e verifica de novo.")
    novo_peso = st.number_input("Trocar o peso para (kg)", min_value=0.1,
                                value=float(alimento.get("peso_kg") or 1) + 1, step=1.0)
    adulterado = copy.deepcopy(documento)
    adulterado.conteudo.setdefault("alimento", {})["peso_kg"] = novo_peso
    _quadro_verificacao(verificar_itens(adulterado, publica))
    st.caption("Mudou um número, mudou o SHA-256: a assinatura deixa de conferir. Por isso o documento é auditável.")

# --- Downloads --------------------------------------------------------------------------------
b = st.columns(3)
try:
    pdf = chamar("GET", f"/v1/lotes/{codigo}/declaracao.pdf", chave, bruto=True)
    b[0].download_button("Baixar PDF", pdf, file_name=f"declaracao-{codigo}.pdf", mime="application/pdf",
                         use_container_width=True)
except ErroAPI as e:
    b[0].caption(f"PDF indisponível: {e.mensagem}")
b[1].download_button("Baixar JSON assinado", json.dumps(documento.para_dict(), ensure_ascii=False, indent=2),
                     file_name=f"declaracao-{codigo}.json", mime="application/json", use_container_width=True)
b[2].download_button("Baixar chave pública", chave_publica["pem"], file_name="chave-publica-rede-alimenta.pem",
                     mime="application/x-pem-file", use_container_width=True)

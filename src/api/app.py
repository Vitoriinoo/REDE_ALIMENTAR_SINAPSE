"""API da Rede Alimenta IA (FastAPI + Swagger em /docs).

Fluxo do cadastro (SDD §4.1): esquema estrito → regras (validade calculada, questionário,
PF só lacrado) → Declaração assinada (RSA-PSS, só inclusão) → Modelo 1 com piso de segurança →
matching (filtros, impasse, disponibilidade mútua, score) → Modelo 2 → oferta à ONG do topo.

Controles transversais (middleware): limite de requisições com freio (regras 10.2), correlação
por requisição no log, cabeçalhos de segurança e log operacional de toda requisição.

Uso local:  uvicorn src.api.app:app --reload
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated

from cryptography.hazmat.primitives import serialization
from fastapi import Depends, FastAPI, HTTPException, Path as PathParam, Request
from fastapi.responses import JSONResponse, Response

from src.api import matching
from src.api.autenticacao import Identidade, Papel, autenticado, credencial, exige, identificar
from src.api.contas import (CadastroRecusado, ContaPendente, Contas, CredencialInvalida, EntradaBloqueada,
                            PedidoCadastro, PedidoLogin, RepositorioContasMemoria, RepositorioContasPostgres)
from src.api.ia import montar_controle
from src.api.repositorio import LoteNaoEncontrado, RepositorioMemoria, RepositorioPostgres
from src.data.curadoria_ipvs import RAIZ
from src.models.controle import ModeloIA
from src.observabilidade.freio import Freio
from src.observabilidade.registro import AuditoriaPostgres, RegistroAuditavel, Resultado, Trilha, correlacao_atual
from src.regras.dominio import Prioridade, TipoDoador
from src.regras.logistica import MAX_RECUSAS_ANTES_DE_ESCALAR
from src.regras.questionario import avaliar
from src.regras.refeicoes import refeicoes
from src.regras.validade import LoteRecusado, em_rota_expressa, validade_efetiva, validar_aceite
from src.seguranca.declaracao import (
    VERSAO_REGRAS,
    assinar,
    chave_id,
    gerar_chave_privada,
    montar_conteudo,
    salvar_par_de_chaves,
    verificar,
    verificar_itens,
)
from src.seguranca.declaracao_pdf import gerar_pdf
from src.seguranca.minimizacao import pseudonimo
from src.seguranca.segredos import SegredoAusente, em_producao
from src.seguranca.senhas import emitir_token, hmac_email
from src.validacao.esquemas import CadastroLote, Entrada, Texto, _enum
from src.validacao.receita import ConsultaBrasilAPI

log = logging.getLogger("api")
BRASILIA = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019
DIR_VAR = Path(os.environ.get("REDE_ALIMENTA_DIR_VAR", RAIZ / "var"))
CODIGO_LOTE = r"^L-API-[0-9A-F]{10}$"


# --- Esquemas de entrada específicos da API (todos herdam de Entrada: strict + extra=forbid) ------
class PedidoSugestao(Entrada):
    texto: Texto


class ConfirmacaoEntrega(Entrada):
    inspecao_aprovada: bool


class AlternarModelo(Entrada):
    modelo: _enum(ModeloIA)
    ligado: bool
    motivo: Texto


# --- Estado da aplicação --------------------------------------------------------------------
class Estado:
    registro: RegistroAuditavel
    controle: object
    info_ia: dict
    repo: object
    cadastro: matching.Cadastro
    chave_declaracao: object
    freio: Freio
    contas: Contas
    receita: object


E = Estado()


def _chave_declaracao():
    pem = os.environ.get("REDE_ALIMENTA_CHAVE_DECLARACAO_PEM")
    if pem:
        # Em .env/Secrets o PEM costuma vir numa linha só, com "\n" literal (barra + n) no lugar das quebras.
        return serialization.load_pem_private_key(pem.replace("\\n", "\n").encode(), password=None)
    if os.environ.get("REDE_ALIMENTA_CHAVE_DECLARACAO"):
        from src.seguranca.declaracao import carregar_chave_privada

        return carregar_chave_privada()
    if em_producao():
        raise SegredoAusente("chave da declaração não configurada")
    exemplo = RAIZ / "segredos" / "chave-declaracao-exemplo.pem"
    if exemplo.exists():
        return serialization.load_pem_private_key(exemplo.read_bytes(), password=None)
    chave = gerar_chave_privada()  # dev sem chave: efêmera, só para dados sintéticos
    salvar_par_de_chaves(chave, DIR_VAR / "chave-dev.pem", DIR_VAR / "chave-dev-publica.pem")
    return chave


def iniciar() -> None:
    url = os.environ.get("REDE_ALIMENTA_DATABASE_URL")
    # Com banco, a trilha de auditoria fica no Supabase: o disco do Render é apagado a cada deploy.
    E.registro = RegistroAuditavel(DIR_VAR / "log", auditoria_db=AuditoriaPostgres(url) if url else None)
    E.controle, E.info_ia = montar_controle(E.registro, DIR_VAR / "interruptores.json")
    E.repo = RepositorioPostgres(url) if url else RepositorioMemoria(DIR_VAR / "declaracoes")
    E.cadastro = matching.Cadastro(RAIZ / "data" / "processed")
    E.chave_declaracao = _chave_declaracao()
    E.contas = Contas(RepositorioContasPostgres(url) if url else RepositorioContasMemoria(DIR_VAR / "contas.json"))
    E.receita = ConsultaBrasilAPI()

    def _ao_mudar(acao, freio):
        E.registro.registrar(Trilha.AUDITORIA, componente="api.freio", acao=acao, ator="sistema", papel="sistema",
                             recurso=f"chave:{freio.chave}", detalhes={"motivo": freio.motivo})

    E.freio = Freio(ao_mudar=_ao_mudar)


@asynccontextmanager
async def _ciclo(_: FastAPI):
    iniciar()
    yield


app = FastAPI(
    title="Rede Alimenta IA",
    version=VERSAO_REGRAS,
    description=(
        "Conecta excedente de alimentos a ONGs na Grande São Paulo. A IA **recomenda** (prioridade, risco de "
        "descarte, categoria a partir do texto) e as **regras no código decidem**. Autenticação: login com e-mail "
        "e senha em `/v1/auth/login` e o token em `Authorization: Bearer`, ou chave de API em `X-Chave-API`. Fonte: https://github.com/Vitoriinoo/REDE_ALIMENTAR_SINAPSE"),
    lifespan=_ciclo,
)


# --- Middleware: correlação, limite/freio, cabeçalhos de segurança, log operacional ------------
@app.middleware("http")
async def _controles(request: Request, chamar):
    correlacao = str(uuid.uuid4())
    token = correlacao_atual.set(correlacao)
    inicio = time.perf_counter()
    chave = credencial(request.headers.get("x-chave-api"), request.headers.get("authorization"))
    sujeito = ("k:" + hashlib.sha256(chave.encode()).hexdigest()[:16]) if chave else (
        "ip:" + (request.client.host if request.client else "?"))
    try:
        if not E.freio.permitir(sujeito, datetime.now(timezone.utc)):
            resposta = JSONResponse({"detail": "limite de requisições excedido"}, status_code=429,
                                    headers={"Retry-After": "60"})
        else:
            resposta = await chamar(request)
        ident = identificar(chave)
        E.registro.registrar(
            Trilha.OPERACIONAL, componente="api", acao="REQUISICAO", ator=ident.ator if ident else sujeito,
            papel=str(ident.papel) if ident else "anonimo", recurso=f"{request.method} {request.url.path}",
            resultado=Resultado.SUCESSO if resposta.status_code < 400 else Resultado.NEGADO,
            detalhes={"status": resposta.status_code, "ms": round((time.perf_counter() - inicio) * 1000, 1)})
        resposta.headers.update({
            "X-Correlacao-Id": correlacao, "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer", "Cache-Control": "no-store",
        })
        return resposta
    finally:
        correlacao_atual.reset(token)


@app.exception_handler(Exception)
async def _erro_inesperado(request: Request, exc: Exception):
    """Nunca devolve stack trace nem mensagem interna (STRIDE I): só o ID para correlacionar no log."""
    log.exception("erro não tratado")
    return JSONResponse({"detail": "erro interno", "correlacao_id": correlacao_atual.get()}, status_code=500)


# --- Rotas ----------------------------------------------------------------------------------
@app.get("/saude", tags=["sistema"])
def saude() -> dict:
    return {"status": "ok", "versao_regras": VERSAO_REGRAS, "banco": E.repo.nome, "ia": E.info_ia["modo"]}


@app.get("/v1/ia", tags=["ia"])
def estado_ia(_: Identidade = Depends(autenticado)) -> dict:
    return {"onde_roda": E.info_ia["modo"], "modelos": E.info_ia["modelos"],
            "ligados": {m.value: E.controle.interruptores.ligado(m) for m in ModeloIA}}


@app.post("/v1/admin/ia", tags=["ia"])
def alternar_modelo(corpo: AlternarModelo, ident: Identidade = Depends(exige(Papel.ADMIN))) -> dict:
    """Interruptor por modelo (regras 10.3): desligado, a regra assume e o sistema continua no ar."""
    E.controle.interruptores.definir(corpo.modelo, corpo.ligado, ident.ator, corpo.motivo)
    return estado_ia(ident)


@app.post("/v1/lotes/sugestao", tags=["lotes"])
def sugerir_categoria(corpo: PedidoSugestao, ident: Identidade = Depends(exige(Papel.DOADOR))) -> dict:
    """Texto livre → guardrail → NLP (Hugging Face). É só SUGESTÃO: o doador confirma no cadastro."""
    rec = E.controle.sugerir_categoria(corpo.texto, ident.ator)
    if rec is None:
        return {"sugestao": None, "mensagem": "Sem sugestão automática: escolha a categoria."}
    return {"sugestao": {k: str(v) for k, v in rec.valor.items()}, "confianca": rec.confianca,
            "modelo": rec.modelo_versao, "requer_confirmacao": True}


def _entradas_m2(lote: CadastroLote, tipo: TipoDoador, doador, prioridade: Prioridade, restante: timedelta,
                 agora_local: datetime, feats: dict) -> dict:
    return {
        "categoria": str(lote.categoria), "armazenamento": str(lote.armazenamento), "tipo_doador": str(tipo),
        "segmento": str(doador.segmento), "regiao": str(doador.regiao), "prioridade": str(prioridade),
        "horas_restantes": round(restante / timedelta(hours=1), 2), "peso_kg": float(lote.peso_kg),
        "hora": agora_local.hour, "dia_semana": agora_local.weekday(),
        "rota_expressa": em_rota_expressa(lote.categoria, lote.armazenamento),
        "fim_de_semana": agora_local.weekday() >= 5, "feriado": False,
        "requer_preparo": bool(lote.questionario.requer_preparo), **feats,
    }


@app.post("/v1/lotes", status_code=201, tags=["lotes"])
def cadastrar_lote(lote: CadastroLote, ident: Identidade = Depends(exige(Papel.DOADOR))) -> dict:
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        doador = E.cadastro.doadores.loc[ident.id]
    except KeyError:
        raise HTTPException(403, "doador sem cadastro ativo") from None
    tipo = TipoDoador(doador.tipo_doador)  # da CONTA, nunca do corpo (checklist, item 1)
    codigo = f"L-API-{uuid.uuid4().hex[:10].upper()}"
    respostas = lote.questionario.para_regra()

    motivos = avaliar(lote.categoria, tipo, respostas)
    validade = validade_efetiva(lote.categoria, lote.armazenamento, preparo=lote.preparo,
                                validade_rotulo=lote.validade_rotulo, saida_refrigeracao=lote.saida_refrigeracao,
                                validade_informada=lote.validade_informada)
    try:
        restante = validar_aceite(lote.categoria, lote.armazenamento, validade, agora)
    except LoteRecusado as e:
        motivos.append("VALIDADE_ABAIXO_DO_MINIMO")
        restante, orientacao = validade - agora, e.motivo
    else:
        orientacao = None

    rota_expressa = em_rota_expressa(lote.categoria, lote.armazenamento)
    conteudo = montar_conteudo(
        lote_id=codigo, doador_pseudonimo=pseudonimo("doador", ident.id), tipo_doador=tipo,
        categoria=lote.categoria, armazenamento=lote.armazenamento, peso_kg=lote.peso_kg, descricao=lote.descricao,
        validade_efetiva=validade,
        base_validade={k: getattr(lote, k) for k in ("preparo", "validade_rotulo", "saida_refrigeracao",
                                                     "validade_informada") if getattr(lote, k) is not None},
        rota_expressa=rota_expressa, respostas=respostas, motivos_bloqueio=motivos, sugestao_ia=None, emitida_em=agora)
    declaracao = assinar(conteudo, E.chave_declaracao)

    base = {
        "codigo": codigo, "origem": "api", "doador_codigo": ident.id, "tipo_doador": str(tipo),
        "segmento": str(doador.segmento), "regiao": str(doador.regiao), "ts_cadastro": agora,
        "categoria": str(lote.categoria), "armazenamento": str(lote.armazenamento), "peso_kg": float(lote.peso_kg),
        "validade_efetiva": validade, "horas_restantes": round(restante / timedelta(hours=1), 2),
        "rota_expressa": rota_expressa, "declaracao_codigo": conteudo["declaracao_id"],
    }
    resposta = {"codigo": codigo, "validade_efetiva": validade.isoformat(),
                "declaracao": {"id": conteudo["declaracao_id"], "sha256": declaracao.sha256,
                               "assinatura": declaracao.algoritmo, "chave_id": declaracao.chave_id}}

    if motivos:
        E.repo.inserir_lote(base | {"status_final": "BLOQUEADO", "bloqueio": "|".join(motivos)})
        E.repo.inserir_declaracao(codigo, declaracao)
        E.repo.inserir_evento(codigo, "BLOQUEIO_CADASTRO", ident.ator, agora, "|".join(motivos))
        E.registro.registrar(Trilha.AUDITORIA, componente="api.lotes", acao="CADASTRO_BLOQUEADO", ator=ident.ator,
                             papel="doador", recurso=f"lote:{codigo}", resultado=Resultado.NEGADO,
                             detalhes={"motivos": motivos, "declaracao_sha256": declaracao.sha256})
        return resposta | {"resultado": "BLOQUEADO", "motivos": motivos, "orientacao": orientacao}

    prio = E.controle.prioridade(lote.categoria, lote.armazenamento, tipo, restante, lote.peso_kg, ident.ator,
                                 f"lote:{codigo}")
    agora_local = agora.astimezone(BRASILIA).replace(tzinfo=None)
    res = matching.ranquear(E.cadastro, ident.id, lote.categoria, lote.armazenamento, lote.peso_kg,
                            bool(lote.questionario.requer_preparo), rota_expressa,
                            validade.astimezone(BRASILIA).replace(tzinfo=None), agora_local,
                            lote.disponivel_ate.astimezone(BRASILIA).replace(tzinfo=None) if lote.disponivel_ate else None)
    risco = E.controle.risco_descarte(
        _entradas_m2(lote, tipo, doador, prio.valor, restante, agora_local, res.features_m2), ident.ator,
        f"lote:{codigo}")

    topo = res.ranking[0] if res.ranking else None
    ranking = [vars(o) for o in res.ranking]
    E.repo.inserir_lote(base | {
        "prioridade": str(prio.valor), "prioridade_fonte": str(prio.fonte),
        "risco_descarte": risco.confianca if risco.confianca is not None else None,
        "ong_codigo": topo.ong_id if topo else None, "modo_logistico": topo.modo if topo else None,
        "excecao_redundante": res.excecao_redundante, "ranking": ranking,
        "status_final": "PENDENTE" if topo else "DESCARTADO",
        "motivo_descarte": None if topo else "SEM_ONG_ELEGIVEL",
    })
    E.repo.inserir_declaracao(codigo, declaracao)
    E.repo.inserir_evento(codigo, "CADASTRO", ident.ator, agora, str(lote.categoria))
    E.repo.inserir_evento(codigo, "TRIAGEM", "sistema", agora, f"{prio.valor} ({prio.fonte})")
    if topo:
        E.repo.inserir_evento(codigo, "OFERTA_ONG", f"ong:{topo.ong_id}", agora, f"score={topo.score}")
    if res.excecao_redundante:
        E.repo.inserir_evento(codigo, "EXCECAO_REDUNDANTE", "sistema", agora, "sem alternativa viável (6.6)")
    E.registro.registrar(Trilha.AUDITORIA, componente="api.lotes", acao="CADASTRO_LOTE", ator=ident.ator,
                         papel="doador", recurso=f"lote:{codigo}",
                         detalhes={"prioridade": str(prio.valor), "fonte": str(prio.fonte),
                                   "risco_alto": bool(risco.valor), "ong_ofertada": topo.ong_id if topo else None,
                                   "exclusoes_matching": res.motivos_exclusao, "declaracao_sha256": declaracao.sha256})
    return resposta | {
        "resultado": "ACEITO" if topo else "SEM_ONG_ELEGIVEL",
        "prioridade": {"valor": str(prio.valor), "fonte": str(prio.fonte), "confianca": prio.confianca},
        "risco_descarte": {"alto": bool(risco.valor), "probabilidade": risco.confianca, "fonte": str(risco.fonte)},
        "ong_ofertada": vars(topo) if topo else None,
        "alternativas": ranking[1:5], "ongs_excluidas": res.motivos_exclusao,
        "refeicoes_estimadas": round(refeicoes(lote.categoria, lote.peso_kg), 1),
    }


CodigoLote = Annotated[str, PathParam(pattern=CODIGO_LOTE)]


def _lote_ou_404(codigo: str) -> dict:
    try:
        return E.repo.lote(codigo)
    except LoteNaoEncontrado:
        raise HTTPException(404, "lote não encontrado") from None


def _oferta_atual(lote: dict, ident: Identidade) -> tuple[int, dict]:
    """A oferta é SEQUENCIAL (regras 6.2): só a ONG da vez (`ong_codigo`) pode aceitar ou recusar."""
    if lote["status_final"] != "PENDENTE" or lote.get("ts_aceite_ong"):
        raise HTTPException(409, "lote não está aguardando aceite")
    ranking = lote.get("ranking") or []
    posicao = next((i for i, o in enumerate(ranking) if o["ong_id"] == ident.id), None)
    if posicao is None or lote.get("ong_codigo") != ident.id:
        raise HTTPException(403, "esta ONG não tem oferta em aberto deste lote")
    return posicao, ranking[posicao]


def _resumo_oferta(lote: dict, ong_id: str) -> dict:
    """O que a ONG vê: o alimento e a logística, nunca quem doou (minimização, regras 11)."""
    oferta = next((o for o in (lote.get("ranking") or []) if o["ong_id"] == ong_id), {})
    return {"codigo": lote["codigo"], "categoria": lote["categoria"], "armazenamento": lote["armazenamento"],
            "peso_kg": float(lote["peso_kg"]), "prioridade": lote.get("prioridade"),
            "validade_efetiva": lote.get("validade_efetiva"), "regiao_doador": lote["regiao"],
            "km": oferta.get("km"), "minutos_ate_receber": oferta.get("minutos_ate_receber"),
            "modo": oferta.get("modo"), "ts_cadastro": lote["ts_cadastro"], "ts_aceite_ong": lote.get("ts_aceite_ong"),
            "refeicoes_estimadas": round(refeicoes(lote["categoria"], float(lote["peso_kg"])), 1)}


@app.post("/v1/auth/cadastro", status_code=201, tags=["autenticação"])
def criar_conta(corpo: PedidoCadastro) -> dict:
    """Conta de doador, ONG ou transportador (admin não tem cadastro aberto).

    ONG só com CNPJ válido e ativo na Receita; Receita fora do ar → conta `pendente`. CPF/CNPJ e
    e-mail são guardados só como HMAC; a senha, só como scrypt."""
    try:
        conta = E.contas.cadastrar(corpo, E.receita)
    except CadastroRecusado as e:
        raise HTTPException(422, str(e)) from None
    E.registro.registrar(Trilha.AUDITORIA, componente="api.contas", acao="CADASTRO_CONTA", ator=conta["codigo"],
                         papel=conta["papel"], recurso=f"conta:{conta['codigo']}", detalhes={"status": conta["status"]})
    return {"id": conta["codigo"], "papel": conta["papel"], "status": conta["status"]}


@app.post("/v1/auth/login", tags=["autenticação"])
def entrar(corpo: PedidoLogin) -> dict:
    """E-mail e senha → token de sessão `ras_...` (8 h). O papel e o ID vêm da conta, nunca do pedido.
    Erro genérico para e-mail ou senha errados; 5 falhas seguidas bloqueiam por 15 min (429)."""
    recurso = f"conta:{hmac_email(corpo.email)[:16]}"
    try:
        conta = E.contas.entrar(corpo.email, corpo.senha)
    except (CredencialInvalida, EntradaBloqueada, ContaPendente) as e:
        status = {CredencialInvalida: 401, EntradaBloqueada: 429, ContaPendente: 403}[type(e)]
        E.registro.registrar(Trilha.AUDITORIA, componente="api.contas", acao="LOGIN", ator="anonimo",
                             papel="anonimo", recurso=recurso, resultado=Resultado.NEGADO,
                             detalhes={"status": status})
        raise HTTPException(status, str(e), headers={"Retry-After": "900"} if status == 429 else None) from None
    token, expira = emitir_token(conta["papel"], conta["codigo"])
    E.registro.registrar(Trilha.AUDITORIA, componente="api.contas", acao="LOGIN", ator=conta["codigo"],
                         papel=conta["papel"], recurso=recurso)
    return {"token": token, "papel": conta["papel"], "id": conta["codigo"], "nome": conta["nome"],
            "expira_em": expira.isoformat()}


@app.get("/v1/eu", tags=["sistema"])
def quem_sou(ident: Identidade = Depends(autenticado)) -> dict:
    """Quem é o dono da credencial: as telas usam para mostrar só o que o papel pode fazer."""
    corpo = {"papel": str(ident.papel), "id": ident.id}
    if ident.papel == Papel.DOADOR:
        try:
            d = E.cadastro.doadores.loc[ident.id]
            corpo |= {"tipo_doador": str(d.tipo_doador), "segmento": str(d.segmento), "regiao": str(d.regiao)}
        except KeyError:
            # Conta nova ainda sem registro operacional: o tipo vem da conta; cadastrar lote fica para depois.
            conta = E.contas.por_codigo(ident.id)
            if conta is None:
                raise HTTPException(403, "doador sem cadastro ativo") from None
            corpo |= {"tipo_doador": conta["tipo_doador"], "cadastro_operacional": False}
    return corpo


@app.get("/v1/doador/lotes", tags=["lotes"])
def meus_lotes(ident: Identidade = Depends(exige(Papel.DOADOR))) -> list[dict]:
    campos = ("codigo", "ts_cadastro", "categoria", "peso_kg", "prioridade", "status_final", "ong_codigo",
              "motivo_descarte", "bloqueio", "refeicoes")
    return [{k: l.get(k) for k in campos} for l in E.repo.do_doador(ident.id)]


@app.get("/v1/ong/ofertas", tags=["ongs"])
def ofertas_da_ong(ident: Identidade = Depends(exige(Papel.ONG))) -> dict:
    return {"ofertas": [_resumo_oferta(l, ident.id) for l in E.repo.ofertas_da_ong(ident.id)],
            "aguardando_entrega": [_resumo_oferta(l, ident.id) for l in E.repo.entregas_da_ong(ident.id)]}


@app.get("/v1/ong/perfil", tags=["ongs"])
def perfil_da_ong(ident: Identidade = Depends(exige(Papel.ONG))) -> dict:
    """Cadastro aprovado da ONG: o que o matching usa para filtrar e ranquear (regras 6)."""
    ongs = E.cadastro.ongs
    linha = ongs[ongs["ong_id"] == ident.id]
    if linha.empty:
        raise HTTPException(404, "ONG sem cadastro aprovado")
    o = linha.iloc[0]
    return {
        "ong_id": ident.id, "regiao": str(o.regiao), "municipio": str(o.municipio), "ipvs_grupo": int(o.ipvs_grupo),
        "lat": round(float(o.lat), 3), "lon": round(float(o.lon), 3), "status_aprovacao": str(o.status_aprovacao),
        "capacidade_kg_dia": float(o.capacidade_kg_dia), "tem_cozinha": bool(o.tem_cozinha),
        "tem_refrigeracao": bool(o.tem_refrigeracao), "tem_freezer": bool(o.tem_freezer),
        "distribui_cestas": bool(o.distribui_cestas), "serve_refeicao": bool(o.serve_refeicao),
        "pode_buscar": bool(o.pode_buscar), "aceita_receber_entrega": bool(o.aceita_receber_entrega),
        "abertura_h": float(o.abertura_h), "fechamento_h": float(o.fechamento_h),
        "turnos": [x for x in str(o.turnos).split("|") if x and x != "nan"],
        "categorias_aceitas": [x for x in str(o.categorias_aceitas).split("|") if x],
    }


@app.get("/v1/ong/historico", tags=["ongs"])
def historico_da_ong(ident: Identidade = Depends(exige(Papel.ONG))) -> list[dict]:
    """O que a ONG já recebeu (ou recusou na inspeção): alimento e resultado, nunca quem doou."""
    return [_resumo_oferta(l, ident.id) | {"status_final": l["status_final"], "ts_entrega": l.get("ts_entrega"),
                                           "refeicoes": l.get("refeicoes"), "motivo_descarte": l.get("motivo_descarte")}
            for l in E.repo.historico_da_ong(ident.id)]


@app.post("/v1/lotes/{codigo}/recusa", tags=["ongs"])
def recusar_lote(codigo: CodigoLote, ident: Identidade = Depends(exige(Papel.ONG))) -> dict:
    """A ONG recusa: a oferta passa para a próxima do ranking. A partir de 3 recusas, escala ao admin (6.2)."""
    lote = _lote_ou_404(codigo)
    posicao, _ = _oferta_atual(lote, ident)
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    ranking = lote.get("ranking") or []
    E.repo.inserir_evento(codigo, "RECUSA_ONG", ident.ator, agora, f"posição {posicao + 1}")
    recusas = posicao + 1
    if recusas >= MAX_RECUSAS_ANTES_DE_ESCALAR:
        E.repo.inserir_evento(codigo, "ESCALADA_ADMIN", "sistema", agora, f"{recusas} recusas")
    proxima = ranking[posicao + 1] if posicao + 1 < len(ranking) else None
    if proxima:
        E.repo.atualizar_desfecho(codigo, ong_codigo=proxima["ong_id"], modo_logistico=proxima["modo"])
        E.repo.inserir_evento(codigo, "OFERTA_ONG", f"ong:{proxima['ong_id']}", agora, f"score={proxima['score']}")
    else:
        E.repo.atualizar_desfecho(codigo, status_final="DESCARTADO", motivo_descarte="NENHUMA_ONG_ACEITOU")
    E.registro.registrar(Trilha.AUDITORIA, componente="api.lotes", acao="RECUSA_ONG", ator=ident.ator, papel="ong",
                         recurso=f"lote:{codigo}",
                         detalhes={"recusas": recusas, "escalado": recusas >= MAX_RECUSAS_ANTES_DE_ESCALAR,
                                   "proxima_ong": proxima["ong_id"] if proxima else None})
    return {"codigo": codigo, "status": "OFERTADO_A_PROXIMA" if proxima else "SEM_ONG",
            "proxima_ong": proxima["ong_id"] if proxima else None,
            "escalado_ao_admin": recusas >= MAX_RECUSAS_ANTES_DE_ESCALAR}


@app.post("/v1/lotes/{codigo}/aceite", tags=["ongs"])
def aceitar_lote(codigo: CodigoLote, ident: Identidade = Depends(exige(Papel.ONG))) -> dict:
    """A ONG da vez aceita a oferta (oferta sequencial, regras 6.2)."""
    lote = _lote_ou_404(codigo)
    _, oferta = _oferta_atual(lote, ident)
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    minutos = round((agora - lote["ts_cadastro"]).total_seconds() / 60, 1)
    E.repo.atualizar_desfecho(codigo, ong_codigo=ident.id, ts_aceite_ong=agora, minutos_ate_match=minutos,
                              modo_logistico=oferta["modo"])
    E.repo.inserir_evento(codigo, "ACEITE_ONG", ident.ator, agora, f"{minutos} min")
    E.registro.registrar(Trilha.AUDITORIA, componente="api.lotes", acao="ACEITE_ONG", ator=ident.ator, papel="ong",
                         recurso=f"lote:{codigo}", detalhes={"minutos_ate_match": minutos})
    return {"codigo": codigo, "status": "ACEITO_PELA_ONG", "minutos_ate_match": minutos, "modo": oferta["modo"]}


@app.post("/v1/lotes/{codigo}/entrega", tags=["ongs"])
def confirmar_entrega(codigo: CodigoLote, corpo: ConfirmacaoEntrega,
                      ident: Identidade = Depends(exige(Papel.ONG))) -> dict:
    """Inspeção na entrega (regras 6.2.1): aprovada → ENTREGUE (conta como kg salvo); reprovada → descarte."""
    lote = _lote_ou_404(codigo)
    if lote.get("ong_codigo") != ident.id or not lote.get("ts_aceite_ong"):
        raise HTTPException(403, "só a ONG que aceitou confirma a entrega")
    if lote["status_final"] != "PENDENTE":
        raise HTTPException(409, "entrega já registrada")
    agora = datetime.now(timezone.utc).replace(microsecond=0)
    if corpo.inspecao_aprovada:
        ref = round(refeicoes(lote["categoria"], float(lote["peso_kg"])), 2)
        E.repo.atualizar_desfecho(codigo, status_final="ENTREGUE", ts_entrega=agora, refeicoes=ref)
        E.repo.inserir_evento(codigo, "ENTREGA", ident.ator, agora, f"{ref} refeições")
    else:
        ref = 0.0
        E.repo.atualizar_desfecho(codigo, status_final="DESCARTADO", ts_entrega=agora,
                                  motivo_descarte="RECUSADO_NA_INSPECAO")
        E.repo.inserir_evento(codigo, "RECUSA_INSPECAO", ident.ator, agora, "inspeção reprovada")
    E.registro.registrar(Trilha.AUDITORIA, componente="api.lotes", acao="CONFIRMACAO_ENTREGA", ator=ident.ator,
                         papel="ong", recurso=f"lote:{codigo}", detalhes={"inspecao_aprovada": corpo.inspecao_aprovada})
    return {"codigo": codigo, "status": "ENTREGUE" if corpo.inspecao_aprovada else "DESCARTADO", "refeicoes": ref}


def _declaracao_do_lote(codigo: str, ident: Identidade):
    lote = _lote_ou_404(codigo)
    if ident.papel != Papel.ADMIN and lote.get("doador_codigo") != ident.id:
        raise HTTPException(404, "lote não encontrado")  # 404 e não 403: não revela que o lote existe
    return E.repo.declaracao(lote["declaracao_codigo"])


@app.get("/v1/lotes/{codigo}/declaracao", tags=["lotes"])
def ver_declaracao(codigo: CodigoLote, ident: Identidade = Depends(autenticado)) -> dict:
    d = _declaracao_do_lote(codigo, ident)
    publica = E.chave_declaracao.public_key()
    itens = verificar_itens(d, publica)
    return d.para_dict() | {"assinatura_valida": all(i["ok"] for i in itens), "verificacao": itens,
                            "chave_id_esperada": chave_id(publica)}


@app.get("/v1/declaracoes/chave-publica", tags=["lotes"])
def chave_publica_declaracoes(_: Identidade = Depends(autenticado)) -> dict:
    """Chave PÚBLICA da plataforma: quem recebe a declaração confere a assinatura sem confiar na API."""
    from cryptography.hazmat.primitives import serialization

    publica = E.chave_declaracao.public_key()
    pem = publica.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    return {"chave_id": chave_id(publica), "pem": pem.decode()}


@app.get("/v1/lotes/{codigo}/declaracao.pdf", tags=["lotes"], response_class=Response)
def baixar_declaracao(codigo: CodigoLote, ident: Identidade = Depends(autenticado)) -> Response:
    d = _declaracao_do_lote(codigo, ident)
    destino = DIR_VAR / "pdf" / f"{codigo}.pdf"
    destino.parent.mkdir(parents=True, exist_ok=True)
    gerar_pdf(d, destino)
    return Response(destino.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="declaracao-{codigo}.pdf"'})


@app.get("/v1/lotes", tags=["lotes"])
def lotes_recentes(_: Identidade = Depends(exige(Papel.ADMIN))) -> list[dict]:
    return [{k: v for k, v in l.items() if k in ("codigo", "regiao", "categoria", "peso_kg", "prioridade",
                                                 "status_final", "ts_cadastro")} for l in E.repo.recentes()]

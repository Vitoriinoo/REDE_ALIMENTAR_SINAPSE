"""Cliente HTTP da API para as telas de operação.

As telas NÃO acessam o banco nem as regras diretamente para agir: tudo passa pela API, com as
mesmas validações, autenticação e log de qualquer outro cliente. A chave de acesso fica só na
sessão do navegador de quem entrou (st.session_state), nunca em arquivo ou segredo do app.
"""

from __future__ import annotations

import httpx

from src.dashboard.dados import API_INTERNA

# O Render grátis "dorme" e leva ~1 min para acordar: timeout generoso na leitura.
TIMEOUT = httpx.Timeout(90.0, connect=10.0)

MOTIVOS = {
    "CATEGORIA_NAO_PERMITIDA_PARA_PF": "Pessoa física só pode doar alimento não perecível lacrado.",
    "EMBALAGEM_VIOLADA": "A embalagem ou o recipiente não está íntegro.",
    "SEM_DECLARACAO": "A declaração de condições do alimento (Lei 14.016/2020) não foi confirmada.",
    "EXPOSTO_AO_CONSUMIDOR": "Alimento exposto ao consumidor (buffet, balcão) não pode ser doado.",
    "ROTULO_AUSENTE": "O rótulo com a validade precisa estar visível.",
    "DESCONGELADO": "Produto já descongelado não pode voltar à cadeia de doação.",
    "PF_SEM_LACRE": "Doação de pessoa física precisa estar lacrada na embalagem original.",
    "HORTIFRUTI_NAO_SELECIONADO": "O hortifrúti precisa estar selecionado (sem partes podres, mofo ou insetos).",
    "VALIDADE_ABAIXO_DO_MINIMO": "A validade restante está abaixo do mínimo para esta categoria.",
    "ALERGENICOS_CONTRADITORIOS": "Marque 'nenhum' OU os alergênicos, não os dois.",
    "SEM_ONG_ELEGIVEL": "Nenhuma ONG consegue receber este lote a tempo agora.",
    "NENHUMA_ONG_ACEITOU": "Todas as ONGs do ranking recusaram.",
    "RECUSADO_NA_INSPECAO": "A ONG recusou o lote na inspeção da entrega.",
}


class ErroAPI(Exception):
    def __init__(self, status: int, mensagem: str):
        super().__init__(mensagem)
        self.status, self.mensagem = status, mensagem


def traduzir(motivo: str) -> str:
    if motivo.startswith("RESPOSTA_FALTANDO:"):
        return f"Falta responder a pergunta {motivo.split(':', 1)[1]}."
    return MOTIVOS.get(motivo, motivo)


def _mensagem(r: httpx.Response) -> str:
    try:
        detalhe = r.json().get("detail")
    except ValueError:
        return f"erro {r.status_code}"
    if isinstance(detalhe, list):  # erro de validação do esquema (422): um item por campo
        partes = []
        for e in detalhe:
            campo = " › ".join(str(x) for x in e.get("loc", [])[1:]) or "dados"
            partes.append(f"{campo}: {e.get('msg', '')}".replace("Value error, ", ""))
        return "; ".join(partes)
    return str(detalhe)


def chamar(metodo: str, rota: str, chave: str | None = None, corpo: dict | None = None, bruto: bool = False):
    cabecalhos = {"X-Chave-API": chave} if chave else {}
    try:
        r = httpx.request(metodo, f"{API_INTERNA}{rota}", headers=cabecalhos, json=corpo, timeout=TIMEOUT)
    except httpx.HTTPError as e:
        raise ErroAPI(0, f"API indisponível ({type(e).__name__}). Se for o Render grátis, aguarde ~1 min e tente de novo.") from None
    if r.status_code >= 400:
        raise ErroAPI(r.status_code, _mensagem(r))
    return r.content if bruto else r.json()

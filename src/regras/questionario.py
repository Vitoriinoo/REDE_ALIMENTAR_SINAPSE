"""Questionário obrigatório do lote (regras, seção 4.5).

As respostas decidem se o lote pode entrar na plataforma e viram a Declaração de
Doação (src/seguranca/declaracao.py). As condições de segurança alimentar ficam AQUI,
no código: nenhum modelo de IA decide se um alimento exposto em buffet pode ser doado.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from src.regras.dominio import Categoria, TipoDoador
from src.regras.logistica import pode_doar


class Origem(StrEnum):
    EXCEDENTE_PRODUCAO = "excedente_producao"
    EXCEDENTE_ESTOQUE = "excedente_estoque"
    SOBRA_EVENTO = "sobra_evento"
    OUTRO = "outro"


class Alergenico(StrEnum):
    """Principais alergênicos da rotulagem obrigatória da ANVISA, agrupados para o doador."""

    NENHUM = "nenhum"
    GLUTEN = "gluten"
    CRUSTACEOS = "crustaceos"
    OVOS = "ovos"
    PEIXES = "peixes"
    AMENDOIM = "amendoim"
    SOJA = "soja"
    LEITE = "leite"
    CASTANHAS = "castanhas"
    NAO_SEI = "nao_sei"


PERGUNTAS: dict[str, str] = {
    "Q1": "Origem do alimento",
    "Q2": "A embalagem ou o recipiente está íntegro (sem furo, estufamento, vazamento ou violação)?",
    "Q3": "Contém alergênicos?",
    "Q4": "Precisa ser cozido ou preparado antes de consumir?",
    "Q5": "Declaração de condições do alimento (Lei 14.016/2020, art. 1º)",
    "Q6": "O alimento ficou exposto ao consumidor (buffet, balcão de autosserviço, mesa)?",
    "Q7": "O rótulo com a validade está visível?",
    "Q8": "O produto foi descongelado alguma vez?",
    "Q9": "Está lacrado na embalagem original de fábrica?",
    "Q10": "Foi selecionado (sem partes podres, mofo ou insetos)?",
}

TEXTO_DECLARACAO = (
    "Declaro que o alimento doado está dentro do prazo de validade e mantém sua integridade, "
    "segurança sanitária e propriedades nutricionais, nos termos do art. 1º da Lei 14.016/2020, "
    "e que as respostas deste questionário são verdadeiras."
)


@dataclass(frozen=True)
class Respostas:
    origem: Origem  # Q1
    embalagem_integra: bool  # Q2
    alergenicos: frozenset[Alergenico]  # Q3
    requer_preparo: bool  # Q4
    declaracao_condicoes: bool  # Q5
    exposto_consumidor: bool | None = None  # Q6 - Preparado
    rotulo_visivel: bool | None = None  # Q7 - Refrigerado, Congelado
    descongelado: bool | None = None  # Q8 - Congelado
    lacrado_original: bool | None = None  # Q9 - doador PF
    selecionado: bool | None = None  # Q10 - Hortifruti


def perguntas_aplicaveis(categoria: Categoria, tipo_doador: TipoDoador) -> list[str]:
    ids = ["Q1", "Q2", "Q3", "Q4", "Q5"]
    if categoria == Categoria.PREPARADO:
        ids.append("Q6")
    if categoria in (Categoria.REFRIGERADO, Categoria.CONGELADO):
        ids.append("Q7")
    if categoria == Categoria.CONGELADO:
        ids.append("Q8")
    if tipo_doador == TipoDoador.PF:
        ids.append("Q9")
    if categoria == Categoria.HORTIFRUTI:
        ids.append("Q10")
    return ids


# Pergunta condicional -> (campo, resposta que BLOQUEIA, motivo).
_CONDICIONAIS = {
    "Q6": ("exposto_consumidor", True, "EXPOSTO_AO_CONSUMIDOR"),
    "Q7": ("rotulo_visivel", False, "ROTULO_AUSENTE"),
    "Q8": ("descongelado", True, "DESCONGELADO"),
    "Q9": ("lacrado_original", False, "PF_SEM_LACRE"),
    "Q10": ("selecionado", False, "HORTIFRUTI_NAO_SELECIONADO"),
}


def avaliar(categoria: Categoria, tipo_doador: TipoDoador, r: Respostas) -> list[str]:
    """Motivos de bloqueio do lote; lista vazia = pode seguir para o matching.

    Resposta obrigatória ausente BLOQUEIA (falha fechada, regras 4.6): o sistema nunca
    presume que a condição sanitária está boa porque o doador não respondeu.
    """
    motivos: list[str] = []
    if not pode_doar(tipo_doador, categoria):
        motivos.append("CATEGORIA_NAO_PERMITIDA_PARA_PF")
    if not r.embalagem_integra:
        motivos.append("EMBALAGEM_VIOLADA")
    if not r.declaracao_condicoes:
        motivos.append("SEM_DECLARACAO")
    if not r.alergenicos:
        motivos.append("RESPOSTA_FALTANDO:Q3")
    elif Alergenico.NENHUM in r.alergenicos and len(r.alergenicos) > 1:
        motivos.append("ALERGENICOS_CONTRADITORIOS")

    for pid in perguntas_aplicaveis(categoria, tipo_doador):
        if pid not in _CONDICIONAIS:
            continue
        campo, valor_que_bloqueia, motivo = _CONDICIONAIS[pid]
        resposta = getattr(r, campo)
        if resposta is None:
            motivos.append(f"RESPOSTA_FALTANDO:{pid}")
        elif resposta == valor_que_bloqueia:
            motivos.append(motivo)
    return motivos

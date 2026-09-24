"""Vocabulário do domínio da Rede Alimenta IA (docs/regras-de-negocio.md)."""

from enum import StrEnum


class Categoria(StrEnum):
    PREPARADO = "preparado"
    REFRIGERADO = "refrigerado"
    CONGELADO = "congelado"
    HORTIFRUTI = "hortifruti"
    PADARIA = "padaria"
    NAO_PERECIVEL = "nao_perecivel"


class Armazenamento(StrEnum):
    REFRIGERADO = "refrigerado"
    CONGELADO = "congelado"
    AMBIENTE = "ambiente"


class TipoDoador(StrEnum):
    PJ = "PJ"
    PF = "PF"


class Prioridade(StrEnum):
    CRITICA = "CRITICA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAIXA = "BAIXA"


class Modalidade(StrEnum):
    ONG_RETIRA = "ong_retira"
    VOLUNTARIO = "voluntario"
    DOADOR_ENTREGA = "doador_entrega"
    MOTORISTA_RETORNO = "motorista_retorno"
    TRANSPORTADORA = "transportadora"
    APP_ENTREGA = "app_entrega"  # única modalidade paga (caixa solidário)


# Ordem de urgência, da mais para a menos urgente.
ORDEM_PRIORIDADE = [Prioridade.CRITICA, Prioridade.ALTA, Prioridade.MEDIA, Prioridade.BAIXA]

CADEIA_FRIA = frozenset({Categoria.PREPARADO, Categoria.REFRIGERADO, Categoria.CONGELADO})

MODALIDADES_GRATUITAS = frozenset(set(Modalidade) - {Modalidade.APP_ENTREGA})

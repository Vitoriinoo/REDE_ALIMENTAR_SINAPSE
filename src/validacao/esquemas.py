"""Esquemas de entrada: TUDO que entra é validado antes de ser considerado (regras, seção 4.6).

Princípio de lista de permissão:
- campo desconhecido é REJEITADO (`extra="forbid"`): ninguém injeta `"aprovado": true`;
- tipos ESTRITOS: "10" não vira 10, "true" não vira True, NaN/infinito são rejeitados;
- datas exigem fuso horário;
- toda faixa, tamanho e lista fechada (enum) é explícita.

Checagens que dependem do relógio recebem o "agora" pelo contexto da validação
(`model_validate(dados, context={"agora": ...})`): o esquema fica determinístico e testável.
Estas classes são a camada 1; regra de negócio (camada 4) continua em src/regras.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Annotated

from pydantic import AfterValidator, AwareDatetime, BaseModel, ConfigDict, Field, ValidationInfo, model_validator

from src.regras.cadastro import PESO_MAXIMO_KG, PESO_MINIMO_KG
from src.regras.dominio import CADEIA_FRIA, Armazenamento, Categoria, TipoDoador, Turno
from src.regras.logistica import PEDIDO_VALIDADE_MAXIMA, categorias_suportadas
from src.regras.questionario import Alergenico, Origem, Respostas
from src.validacao.documentos import cnpj_valido, cpf_valido, normalizar

# --- Limites (regras 4.6) ------------------------------------------------------------------
TOLERANCIA_RELOGIO = timedelta(minutes=5)
PREPARO_MAXIMO_ATRAS = timedelta(hours=72)
SAIDA_REFRIGERACAO_MAXIMA_ATRAS = timedelta(hours=24)
VALIDADE_MAXIMA_A_FRENTE = timedelta(days=730)
# Caixa geográfica do recorte (RMSP, 8 municípios) com margem de ~5 km.
LAT_MIN, LAT_MAX = -24.05, -23.25
LON_MIN, LON_MAX = -46.90, -46.20

_CONTROLE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f​-‏ -‮⁠-⁤﻿]")

ARMAZENAMENTOS_PERMITIDOS: dict[Categoria, frozenset[Armazenamento]] = {
    Categoria.PREPARADO: frozenset({Armazenamento.REFRIGERADO, Armazenamento.AMBIENTE}),
    Categoria.REFRIGERADO: frozenset({Armazenamento.REFRIGERADO, Armazenamento.AMBIENTE}),
    Categoria.CONGELADO: frozenset({Armazenamento.CONGELADO, Armazenamento.AMBIENTE}),
}


def _sem_controle(texto: str) -> str:
    if _CONTROLE.search(texto):
        raise ValueError("contém caracteres de controle ou invisíveis")
    return texto


Texto = Annotated[str, Field(min_length=3, max_length=500), AfterValidator(_sem_controle)]
Nome = Annotated[str, Field(min_length=2, max_length=120), AfterValidator(_sem_controle)]
Email = Annotated[str, Field(max_length=254, pattern=r"^[A-Za-z0-9._%+-]{1,64}@[A-Za-z0-9.-]{1,185}\.[A-Za-z]{2,24}$")]
TelefoneBR = Annotated[str, Field(pattern=r"^\+55[1-9][0-9]{9,10}$")]  # E.164: +55 DDD número
Cep = Annotated[str, Field(pattern=r"^[0-9]{8}$")]
Latitude = Annotated[float, Field(ge=LAT_MIN, le=LAT_MAX, allow_inf_nan=False)]
Longitude = Annotated[float, Field(ge=LON_MIN, le=LON_MAX, allow_inf_nan=False)]
Hora = Annotated[float, Field(ge=0, le=24, allow_inf_nan=False)]
Data = Annotated[AwareDatetime, Field(strict=False)]  # aceita ISO 8601 do JSON, mas exige fuso


def _enum(tipo):
    """Enum aceita o valor em texto (vindo do JSON), mas só dentro da lista fechada."""
    return Annotated[tipo, Field(strict=False)]


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True)


def _agora(info: ValidationInfo) -> datetime:
    agora = (info.context or {}).get("agora")
    return agora if agora is not None else datetime.now(timezone.utc)


# --- Lote -----------------------------------------------------------------------------------
class RespostasQuestionario(Entrada):
    origem: _enum(Origem)
    embalagem_integra: bool
    alergenicos: Annotated[frozenset[_enum(Alergenico)], Field(strict=False, min_length=1, max_length=len(Alergenico))]
    requer_preparo: bool
    declaracao_condicoes: bool
    exposto_consumidor: bool | None = None
    rotulo_visivel: bool | None = None
    descongelado: bool | None = None
    lacrado_original: bool | None = None
    selecionado: bool | None = None

    def para_regra(self) -> Respostas:
        return Respostas(**self.model_dump())


class CadastroLote(Entrada):
    descricao: Texto
    categoria: _enum(Categoria)  # já CONFIRMADA pelo doador (a sugestão da IA nunca vem do cliente)
    armazenamento: _enum(Armazenamento)
    peso_kg: Annotated[float, Field(ge=PESO_MINIMO_KG, le=PESO_MAXIMO_KG, allow_inf_nan=False)]
    preparo: Data | None = None
    validade_rotulo: Data | None = None
    saida_refrigeracao: Data | None = None
    validade_informada: Data | None = None
    questionario: RespostasQuestionario


    @model_validator(mode="after")
    def _coerencia(self, info: ValidationInfo) -> CadastroLote:
        cat, arm = self.categoria, self.armazenamento
        permitidos = ARMAZENAMENTOS_PERMITIDOS.get(cat)
        if permitidos is not None and arm not in permitidos:
            raise ValueError(f"armazenamento '{arm}' não se aplica a {cat}")

        # Cada categoria exige exatamente os campos de validade que a regra 4.2 usa.
        exigidos: set[str]
        if cat == Categoria.PREPARADO:
            exigidos = {"preparo"}
        elif cat in CADEIA_FRIA:
            exigidos = {"validade_rotulo"} | ({"saida_refrigeracao"} if arm == Armazenamento.AMBIENTE else set())
        else:
            exigidos = {"validade_informada"}
        campos = {"preparo", "validade_rotulo", "saida_refrigeracao", "validade_informada"}
        presentes = {c for c in campos if getattr(self, c) is not None}
        if faltando := exigidos - presentes:
            raise ValueError(f"campo(s) obrigatório(s) para {cat}: {sorted(faltando)}")
        if sobrando := presentes - exigidos:
            raise ValueError(f"campo(s) que não se aplicam a {cat}: {sorted(sobrando)}")

        agora = _agora(info)
        if self.preparo is not None and not (agora - PREPARO_MAXIMO_ATRAS <= self.preparo <= agora + TOLERANCIA_RELOGIO):
            raise ValueError("hora do preparo deve estar entre 72 h atrás e agora")
        if self.saida_refrigeracao is not None and not (
            agora - SAIDA_REFRIGERACAO_MAXIMA_ATRAS <= self.saida_refrigeracao <= agora + TOLERANCIA_RELOGIO
        ):
            raise ValueError("saída da refrigeração deve estar entre 24 h atrás e agora")
        for campo in ("validade_rotulo", "validade_informada"):
            valor = getattr(self, campo)
            if valor is not None and valor > agora + VALIDADE_MAXIMA_A_FRENTE:
                raise ValueError(f"{campo} acima de 2 anos à frente")
        return self


# --- Cadastro de pessoas e entidades --------------------------------------------------------------
class _Contato(Entrada):
    nome: Nome
    email: Email
    telefone: TelefoneBR
    cep: Cep
    lat: Latitude
    lon: Longitude



class CadastroDoador(_Contato):
    tipo: _enum(TipoDoador)
    documento: Annotated[str, Field(min_length=11, max_length=18)]
    pode_entregar: bool
    tem_refrigeracao: bool
    aceita_aviso_de_pedidos: bool = False

    @model_validator(mode="after")
    def _documento(self) -> CadastroDoador:
        valido = cpf_valido(self.documento) if self.tipo == TipoDoador.PF else cnpj_valido(self.documento)
        if not valido:
            raise ValueError("documento inválido para o tipo de doador (dígito verificador)")
        return self

    @property
    def documento_normalizado(self) -> str:
        return normalizar(self.documento)


class CadastroOng(_Contato):
    cnpj: Annotated[str, Field(min_length=14, max_length=18)]
    capacidade_kg_dia: Annotated[float, Field(ge=1, le=10_000, allow_inf_nan=False)]
    capacidade_refrigerada_kg: Annotated[float, Field(ge=0, le=10_000, allow_inf_nan=False)] = 0.0
    tem_refrigeracao: bool
    tem_freezer: bool
    tem_cozinha: bool
    distribui_cestas: bool
    pode_buscar: bool
    abertura_h: Hora
    fechamento_h: Hora
    turnos: Annotated[frozenset[_enum(Turno)], Field(strict=False, max_length=len(Turno))] = frozenset()
    categorias_aceitas: Annotated[frozenset[_enum(Categoria)], Field(strict=False, min_length=1, max_length=len(Categoria))]

    @model_validator(mode="after")
    def _coerencia(self) -> CadastroOng:
        if not cnpj_valido(self.cnpj):
            raise ValueError("CNPJ inválido (dígito verificador)")
        if self.abertura_h >= self.fechamento_h:
            raise ValueError("a janela de recebimento deve abrir antes de fechar")
        if self.tem_freezer and not self.tem_refrigeracao:
            raise ValueError("freezer exige declarar refrigeração")
        if self.capacidade_refrigerada_kg > self.capacidade_kg_dia:
            raise ValueError("capacidade refrigerada maior que a capacidade total")
        if (self.capacidade_refrigerada_kg > 0) != self.tem_refrigeracao:
            raise ValueError("capacidade refrigerada incoerente com a refrigeração declarada")
        if fora := self.categorias_aceitas - categorias_suportadas(self.tem_refrigeracao, self.tem_freezer):
            raise ValueError(f"a estrutura declarada não comporta: {sorted(map(str, fora))}")
        return self


class PedidoOng(Entrada):
    categoria: _enum(Categoria)
    kg: Annotated[float, Field(gt=0, le=10_000, allow_inf_nan=False)]
    validade_dias: Annotated[int, Field(ge=1, le=PEDIDO_VALIDADE_MAXIMA.days)]
    observacao: Annotated[str, Field(max_length=200), AfterValidator(_sem_controle)] = ""


class RespostaOferta(Entrada):
    lote_id: Annotated[str, Field(pattern=r"^L-[0-9]{6}$")]
    aceita: bool
    motivo_recusa: Annotated[str, Field(pattern=r"^(sem_capacidade|fora_do_horario|categoria|qualidade|outro)$")] | None = None

    @model_validator(mode="after")
    def _motivo(self) -> RespostaOferta:
        if not self.aceita and self.motivo_recusa is None:
            raise ValueError("recusa exige motivo")
        return self

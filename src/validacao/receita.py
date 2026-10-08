"""Verificação do CNPJ na Receita Federal via BrasilAPI (regras, seção 6.3).

Três passos: dígito verificador (formato) -> consulta à Receita (existe e está ativo)
-> aprovação humana (legitimidade, feita pelo admin fora deste módulo).

A resposta da BrasilAPI também é ENTRADA NÃO CONFIÁVEL (regras 4.6): é validada por
esquema e só os campos necessários são lidos. O resto (inclusive o quadro de sócios,
que tem dados pessoais) é descartado na hora: minimização (LGPD).

Falha fechada: se a consulta falhar ou vier fora do esquema, o cadastro fica PENDENTE
de revisão manual. Nunca é aprovado por omissão.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.validacao.documentos import cnpj_valido, normalizar

URL_BRASILAPI = "https://brasilapi.com.br/api/cnpj/v1/{cnpj}"
TIMEOUT_S = 5.0
CACHE_TTL_S = 24 * 3600

SITUACAO_ATIVA = 2
# Tabela de Natureza Jurídica (CONCLA/IBGE): entidades sem fins lucrativos aceitas como ONG.
NATUREZAS_ONG = {
    3069: "Fundação Privada",
    3204: "Estabelecimento, no Brasil, de Fundação ou Associação Estrangeiras",
    3220: "Organização Religiosa",
    3301: "Organização Social (OS)",
    3999: "Associação Privada",
}
# CNAE (7 dígitos) do ramo de alimentos: agricultura, pesca, indústria de alimentos,
# atacado e varejo de alimentos, alimentação (restaurantes, bufês).
PREFIXOS_CNAE_ALIMENTOS = ("01", "03", "10", "463", "4711", "4712", "472", "56")


class Resultado(StrEnum):
    VALIDO = "VALIDO"  # ONG: ainda depende da aprovação do admin (6.3)
    REVISAO_ADMIN = "REVISAO_ADMIN"
    PENDENTE = "PENDENTE"  # consulta indisponível: falha fechada
    REJEITADO = "REJEITADO"


@dataclass(frozen=True)
class VerificacaoCnpj:
    resultado: Resultado
    motivo: str
    fonte: str
    codigo_natureza_juridica: int | None = None
    cnae_fiscal: str | None = None


class DadosReceita(BaseModel):
    """Só o que a regra precisa. `extra="ignore"` descarta o resto da resposta."""

    model_config = ConfigDict(extra="ignore", frozen=True)

    cnpj: str = Field(pattern=r"^[0-9A-Z]{14}$")
    situacao_cadastral: int = Field(ge=1, le=8)
    descricao_situacao_cadastral: str = Field(max_length=40)
    codigo_natureza_juridica: int = Field(ge=1000, le=9999)
    cnae_fiscal: int = Field(ge=100_000, le=9_999_999)


class ConsultaReceita(Protocol):
    nome: str

    def consultar(self, cnpj: str) -> dict | None:
        """Resposta bruta da Receita, ou None se o CNPJ não existe. Levanta exceção se indisponível."""


class ConsultaBrasilAPI:
    nome = "brasilapi"

    def __init__(self, timeout_s: float = TIMEOUT_S, ttl_s: float = CACHE_TTL_S):
        import httpx  # import tardio: os testes usam a consulta simulada

        self._cliente = httpx.Client(timeout=timeout_s, follow_redirects=False)
        self._ttl = ttl_s
        self._cache: dict[str, tuple[float, dict | None]] = {}

    def consultar(self, cnpj: str) -> dict | None:
        agora = time.monotonic()
        if cnpj in self._cache and agora - self._cache[cnpj][0] < self._ttl:
            return self._cache[cnpj][1]
        resposta = self._cliente.get(URL_BRASILAPI.format(cnpj=cnpj))
        if resposta.status_code == 404:
            dados = None
        else:
            resposta.raise_for_status()
            dados = resposta.json()
        self._cache[cnpj] = (agora, dados)
        return dados


class ConsultaSimulada:
    """Base local de CNPJs para testes e demonstração (sem rede)."""

    nome = "simulada"

    def __init__(self, base: dict[str, dict], indisponivel: bool = False):
        self._base = base
        self._indisponivel = indisponivel

    def consultar(self, cnpj: str) -> dict | None:
        if self._indisponivel:
            raise ConnectionError("Receita indisponível (simulado)")
        return self._base.get(cnpj)


def verificar_cnpj(cnpj: str, papel: Literal["ong", "doador"], consulta: ConsultaReceita) -> VerificacaoCnpj:
    c = normalizar(cnpj)
    if not cnpj_valido(c):
        return VerificacaoCnpj(Resultado.REJEITADO, "digito_verificador_invalido", "calculo")

    try:
        bruto = consulta.consultar(c)
    except Exception:  # noqa: BLE001 - qualquer falha externa vira PENDENTE (falha fechada)
        return VerificacaoCnpj(Resultado.PENDENTE, "receita_indisponivel", consulta.nome)
    if bruto is None:
        return VerificacaoCnpj(Resultado.REJEITADO, "cnpj_inexistente", consulta.nome)
    try:
        dados = DadosReceita.model_validate(bruto)
    except ValidationError:
        return VerificacaoCnpj(Resultado.PENDENTE, "resposta_fora_do_esquema", consulta.nome)
    if dados.cnpj != c:
        return VerificacaoCnpj(Resultado.PENDENTE, "resposta_de_outro_cnpj", consulta.nome)

    cnae = str(dados.cnae_fiscal).zfill(7)
    base = {"fonte": consulta.nome, "codigo_natureza_juridica": dados.codigo_natureza_juridica, "cnae_fiscal": cnae}
    if dados.situacao_cadastral != SITUACAO_ATIVA:
        return VerificacaoCnpj(Resultado.REJEITADO, "cnpj_nao_ativo", **base)
    if papel == "ong":
        if dados.codigo_natureza_juridica not in NATUREZAS_ONG:
            return VerificacaoCnpj(Resultado.REJEITADO, "natureza_juridica_incompativel_com_ong", **base)
        return VerificacaoCnpj(Resultado.VALIDO, "ativo_sem_fins_lucrativos", **base)
    if not cnae.startswith(PREFIXOS_CNAE_ALIMENTOS):
        return VerificacaoCnpj(Resultado.REVISAO_ADMIN, "cnae_fora_do_ramo_de_alimentos", **base)
    return VerificacaoCnpj(Resultado.VALIDO, "ativo_ramo_alimentos", **base)

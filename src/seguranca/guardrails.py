"""Guardrail de entrada para o texto livre do doador (regras 4.4; aula 4, "filtro de entrada").

O texto do doador é DADO NÃO CONFIÁVEL: nunca vira instrução para o modelo nem para
o sistema. Este filtro roda ANTES do classificador e:
- limita o tamanho (consumo de recursos / negação de serviço);
- remove marcação HTML e caracteres de controle;
- bloqueia padrões conhecidos de prompt injection e de injeção de código/SQL,
  depois de normalizar ofuscações (unicode de largura total, caracteres invisíveis,
  leetspeak).

Limitação assumida: filtro por padrões é contornável. Ele reduz a superfície, mas a
defesa principal é arquitetural: o classificador só escolhe rótulos de uma lista
fixa, o doador confirma e as regras de negócio revalidam (ver src/models/nlp.py).

Histórico: v1 -> v2 (reteste da aula 9). A v1 bloqueava 2/10 ataques inéditos do
conjunto A e dava falso positivo em "Sistema: câmara fria...". A v2 adiciona a
normalização e padrões generalizados a partir do conjunto A (o conjunto B fica
reservado para medir a generalização).
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

VERSAO = "v2"
TAMANHO_MAXIMO = 500

_LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "@": "a", "$": "s"})

PADROES_BLOQUEIO: dict[str, re.Pattern] = {
    "prompt_injection": re.compile(
        r"(ignor[ea]\w*\s+(\w+\s+){0,3}(instru|regra|pol[ií]tica|orienta)"
        r"|desconsider\w*\s+(\w+\s+){0,4}(dito|instru|regra|orienta|anterior|pol[ií]tica)"
        r"|esque[çc]a\s+(\w+\s+){0,3}(instru|regra)"
        r"|voc[êe]\s+agora\s+[ée]"
        r"|\b(aja|atue)\s+como\s+(o\s+|a\s+)?(admin|administrador|gestor|sistema)"
        r"|\bpara\s+o\s+modelo\b"
        r"|nova\s+instru[çc][ãa]o"
        r"|revele\s|responda\s+apenas"
        r"|^\s*#{2,})",
        re.IGNORECASE | re.MULTILINE,
    ),
    "html_script": re.compile(r"<\s*/?\s*(script|iframe|img|svg|object|embed)\b|javascript:|on\w+\s*=", re.IGNORECASE),
    "sql_injection": re.compile(r"('|\")\s*;|;\s*(drop|delete|insert|update|alter|truncate)\b|--\s*$|\bunion\s+select\b",
                                re.IGNORECASE | re.MULTILINE),
}
_TAGS = re.compile(r"<[^>]{0,200}>")
_ESPACOS = re.compile(r"\s+")


@dataclass
class ResultadoGuardrail:
    texto: str
    bloqueado: bool
    motivos: list[str] = field(default_factory=list)


def _sem_invisiveis(texto: str) -> str:
    """Remove caracteres de controle e de formatação (ex.: zero-width space), mantendo quebras de linha."""
    return "".join(c for c in texto if unicodedata.category(c)[0] != "C" or c in "\n\t")


def _normalizar_para_deteccao(texto: str) -> str:
    """Cópia usada SÓ para detectar padrões (o texto limpo devolvido não sofre o leetspeak)."""
    return _sem_invisiveis(unicodedata.normalize("NFKC", texto)).translate(_LEET)


def filtrar_entrada(texto: str) -> ResultadoGuardrail:
    motivos: list[str] = []
    if len(texto) > TAMANHO_MAXIMO:
        motivos.append("entrada_gigante")

    # Avalia só o início do texto para não gastar CPU com entradas gigantes.
    trecho = texto[: TAMANHO_MAXIMO * 2]
    normalizado = _normalizar_para_deteccao(trecho)
    for nome, padrao in PADROES_BLOQUEIO.items():
        alvo = trecho if nome == "sql_injection" else normalizado  # SQL depende de dígitos literais
        if padrao.search(alvo) or padrao.search(trecho):
            motivos.append(nome)

    limpo = html.unescape(unicodedata.normalize("NFKC", texto[:TAMANHO_MAXIMO]))
    limpo = _TAGS.sub(" ", limpo)
    limpo = _ESPACOS.sub(" ", _sem_invisiveis(limpo)).strip()
    return ResultadoGuardrail(texto=limpo, bloqueado=bool(motivos), motivos=motivos)

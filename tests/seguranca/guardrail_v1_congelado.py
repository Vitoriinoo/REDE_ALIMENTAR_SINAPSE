"""[CÓPIA CONGELADA DA v1: linha de base do reteste, não usar em produção]

Guardrail de entrada para o texto livre do doador (regras 4.4; aula 4, "filtro de entrada").

O texto do doador é DADO NÃO CONFIÁVEL: nunca vira instrução para o modelo nem para
o sistema. Este filtro roda ANTES do classificador e:
- limita o tamanho (consumo de recursos / negação de serviço);
- remove marcação HTML e caracteres de controle;
- bloqueia padrões conhecidos de prompt injection e de injeção de código/SQL.

O bloqueio é conservador: o doador recebe uma mensagem genérica e pode preencher o
formulário estruturado. O evento é registrado para investigação.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field

TAMANHO_MAXIMO = 500

PADROES_BLOQUEIO: dict[str, re.Pattern] = {
    "prompt_injection": re.compile(
        r"(ignor[ea]\w*\s+(as\s+|todas\s+as\s+)?(instru|regra|pol[ií]tica)"
        r"|esque[çc]a\s+(as\s+|todas\s+as\s+)?(instru|regra)"
        r"|voc[êe]\s+agora\s+[ée]"
        r"|\bsistema\s*:"
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


def filtrar_entrada(texto: str) -> ResultadoGuardrail:
    motivos: list[str] = []
    if len(texto) > TAMANHO_MAXIMO:
        motivos.append("entrada_gigante")

    for nome, padrao in PADROES_BLOQUEIO.items():
        # Avalia só o início do texto para não gastar CPU com entradas gigantes.
        if padrao.search(texto[: TAMANHO_MAXIMO * 2]):
            motivos.append(nome)

    limpo = html.unescape(texto[:TAMANHO_MAXIMO])
    limpo = _TAGS.sub(" ", limpo)
    limpo = "".join(c for c in limpo if unicodedata.category(c)[0] != "C" or c in "\n\t")
    limpo = _ESPACOS.sub(" ", limpo).strip()
    return ResultadoGuardrail(texto=limpo, bloqueado=bool(motivos), motivos=motivos)

"""PDF legível da Declaração de Doação (regras 4.5).

O documento OFICIAL é o JSON assinado; o PDF é só a representação para pessoas e
imprime o SHA-256 e a assinatura para que qualquer um confira contra o JSON.
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

from fpdf import FPDF

from src.seguranca.declaracao import DeclaracaoAssinada


def _latin1(texto: str) -> str:
    """As fontes padrão do PDF são Latin-1: troca o que não cabe (o JSON guarda o original)."""
    return str(texto).replace("—", "-").replace("–", "-").replace("≥", ">=").replace("≤", "<=").encode(
        "latin-1", "replace").decode("latin-1")


def _resposta(valor) -> str:
    if valor is True:
        return "Sim"
    if valor is False:
        return "Não"
    if isinstance(valor, list):
        return ", ".join(valor)
    return str(valor)


def gerar_pdf(declaracao: DeclaracaoAssinada, destino: Path) -> Path:
    c = declaracao.conteudo
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    largura = pdf.w - pdf.l_margin - pdf.r_margin

    def linha(texto: str, tamanho: int = 10, estilo: str = "", altura: float = 5.5) -> None:
        pdf.set_font("Helvetica", estilo, tamanho)
        pdf.multi_cell(largura, altura, _latin1(texto), new_x="LMARGIN", new_y="NEXT")

    linha("Rede Alimenta IA - Declaração de Doação", 15, "B", 8)
    linha(f"Resultado: {c['resultado']}" + (f"  ({', '.join(c['motivos_bloqueio'])})" if c["motivos_bloqueio"] else ""),
          11, "B")
    linha(f"Declaração {c['declaracao_id']}  ·  versão {c['versao']}  ·  emitida em {c['emitida_em']} (UTC)")
    linha(f"Lote {c['lote_id']}  ·  doador {c['doador']['pseudonimo']} ({c['doador']['tipo']})  ·  regras v{c['versao_regras']}")
    pdf.ln(3)

    a = c["alimento"]
    linha("Alimento", 12, "B", 7)
    linha(f"Descrição: {a['descricao']}")
    linha(f"Categoria: {a['categoria_confirmada']}  ·  armazenamento: {a['armazenamento_confirmado']}  ·  "
          f"peso: {a['peso_kg']} kg  ·  rota expressa: {_resposta(a['rota_expressa'])}")
    linha(f"Validade efetiva (calculada pelo sistema): {a['validade_efetiva']}")
    if c.get("sugestao_ia"):
        s = c["sugestao_ia"]
        linha(f"Sugestão da IA: {s.get('categoria')} (confiança {s.get('confianca')}, modelo {s.get('modelo')}); "
              f"confirmada pelo doador: {a['categoria_confirmada']}")
    pdf.ln(3)

    linha("Questionário", 12, "B", 7)
    for pid, item in c["questionario"].items():
        linha(f"{pid}. {item['pergunta']}", 9, "B", 5)
        linha(f"     {_resposta(item['resposta'])}", 9)
    pdf.ln(2)
    linha(c["texto_declaracao"], 9, "I")
    pdf.ln(4)

    linha("Integridade", 12, "B", 7)
    linha(f"Algoritmo: {declaracao.algoritmo}  ·  chave: {declaracao.chave_id}", 8)
    linha(f"SHA-256 do JSON canônico: {declaracao.sha256}", 8)
    if c.get("hash_versao_anterior"):
        linha(f"Versão anterior (SHA-256): {c['hash_versao_anterior']}", 8)
    linha("Assinatura (base64):", 8)
    pdf.set_font("Courier", "", 6)
    for trecho in textwrap.wrap(declaracao.assinatura, 110):
        pdf.cell(largura, 3, trecho, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    linha("Para verificar: recalcule o SHA-256 do JSON canônico (chaves ordenadas, UTF-8, sem espaços) e "
          "valide a assinatura com a chave pública da plataforma.", 7, "I", 4)

    destino.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(destino))
    # O JSON assinado vai junto, ao lado do PDF, para conferência.
    destino.with_suffix(".json").write_text(json.dumps(declaracao.para_dict(), ensure_ascii=False, indent=1),
                                            encoding="utf-8")
    return destino

"""Resumo dos relatórios de segurança (Bandit e Trivy) para o dashboard e o security gate.

Lê os JSON das ferramentas em `reports/sast/` e grava `reports/sast/resumo.json`:
- contagem por severidade ANTES (primeira varredura, guardada como evidência) e DEPOIS (atual);
- a lista de achados mitigados, com o risco e a correção aplicada;
- o veredito do gate: falha se houver achado ALTO/CRÍTICO aberto (SDD §8).

Uso:
    python -m src.seguranca.relatorio_sast            # gera o resumo
    python -m src.seguranca.relatorio_sast --gate     # e sai com erro se o gate reprovar
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from datetime import datetime, timezone

from src.data.curadoria_ipvs import RAIZ

DIR = RAIZ / "reports" / "sast"
SEVERIDADES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]

# O que foi feito para cada regra do Bandit encontrada na primeira varredura.
CORRECOES_BANDIT = {
    "B613": ("Caracteres bidirecionais Unicode literais no código-fonte (ataque Trojan Source, CVE-2021-42574): "
             "o código exibido pode ser diferente do executado",
             "Caracteres reescritos como escapes ASCII (\\u200f...) no regex que barra invisíveis"),
    "B608": ("SQL montado com f-string a partir das chaves de um dicionário: um nome de coluna vindo de fora "
             "viraria injeção de SQL",
             "Allowlist de colunas + psycopg.sql.Identifier; valores sempre como parâmetros"),
    "B101": ("assert usado como controle (allowlist de colunas, invariantes): o Python remove assert com -O",
             "Trocado por exceção explícita (ValueError/RuntimeError)"),
}


def _bandit(caminho) -> tuple[Counter, list[dict]]:
    if not caminho.exists():
        return Counter(), []
    d = json.loads(caminho.read_text(encoding="utf-8"))
    achados = d.get("results", [])
    return Counter(r["issue_severity"] for r in achados), achados


def _trivy(caminho) -> Counter:
    if not caminho.exists():
        return Counter()
    d = json.loads(caminho.read_text(encoding="utf-8"))
    return Counter(v["Severity"] for r in d.get("Results", []) or [] for v in r.get("Vulnerabilities", []) or [])


def _contagem(c: Counter) -> dict:
    return {s: int(c.get(s, 0)) for s in SEVERIDADES}


def gerar() -> dict:
    antes, achados_antes = _bandit(DIR / "bandit-antes.json")
    depois, achados_depois = _bandit(DIR / "bandit.json")
    abertos = {(r["test_id"], r["filename"].replace("\\", "/"), r["line_number"]) for r in achados_depois}
    mitigados = [
        {"ferramenta": "Bandit", "regra": r["test_id"], "severidade": r["issue_severity"],
         "arquivo": r["filename"].replace("\\", "/"), "risco": CORRECOES_BANDIT.get(r["test_id"], ("", ""))[0],
         "correcao": CORRECOES_BANDIT.get(r["test_id"], ("", ""))[1]}
        for r in achados_antes if (r["test_id"], r["filename"].replace("\\", "/"), r["line_number"]) not in abertos
    ]
    trivy = {}
    for alvo in ("api", "inferencia", "dashboard", "dependencias"):
        a, d = _trivy(DIR / f"trivy-{alvo}-antes.json"), _trivy(DIR / f"trivy-{alvo}.json")
        if a or d or (DIR / f"trivy-{alvo}.json").exists():
            trivy[alvo] = {"antes": _contagem(a), "depois": _contagem(d)}
    mitigacoes_trivy = json.loads((DIR / "mitigacoes-trivy.json").read_text(encoding="utf-8")) \
        if (DIR / "mitigacoes-trivy.json").exists() else []

    altos_abertos = depois.get("HIGH", 0) + sum(t["depois"]["CRITICAL"] + t["depois"]["HIGH"] for t in trivy.values())
    resumo = {
        "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "bandit": {"antes": _contagem(antes), "depois": _contagem(depois)},
        "trivy": trivy,
        "mitigados": mitigados + mitigacoes_trivy,
        "gate": {"regra": "0 achados ALTO/CRÍTICO abertos (Bandit + Trivy, com correção disponível)",
                 "altos_ou_criticos_abertos": int(altos_abertos), "aprovado": altos_abertos == 0},
    }
    (DIR / "resumo.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumo


if __name__ == "__main__":
    r = gerar()
    print(json.dumps({k: r[k] for k in ("bandit", "trivy", "gate")}, ensure_ascii=False))
    if "--gate" in sys.argv and not r["gate"]["aprovado"]:
        sys.exit("security gate REPROVADO: há achado ALTO/CRÍTICO aberto")

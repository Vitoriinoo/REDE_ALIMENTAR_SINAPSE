"""Avaliação do classificador de texto livre e do guardrail de entrada.

- Classificador padrão (similaridade) na MESMA amostra estratificada do teste usada pelo
  baseline NLI (predições do NLI salvas em reports/nlp_predicoes_baseline_nli.csv;
  para recalcular, `--com-nli`, ~16 min em CPU).
- Conjunto independente (tests/dados/avaliacao_independente_nlp.csv), se preenchido.
- Guardrail: adversariais do dataset, ataques inéditos A e B, benignos suspeitos (v1 x atual).

Uso:
    python -m src.models.avaliar_nlp [--com-nli]
"""

from __future__ import annotations

import json
import sys
import time

import pandas as pd
from sklearn.metrics import accuracy_score, confusion_matrix

from src.models import features as F
from src.models.nlp import (
    MODELO_EMBEDDINGS,
    MODELO_NLI,
    REVISAO_EMBEDDINGS,
    REVISAO_NLI,
    ClassificadorSimilaridade,
    ClassificadorZeroShotNLI,
)
from src.regras.dominio import CADEIA_FRIA, Categoria
from src.seguranca import guardrails
from tests.seguranca import guardrail_v1_congelado as guardrail_v1
from tests.seguranca.ataques_ineditos import BENIGNOS_SUSPEITOS, CONJUNTO_A, CONJUNTO_B

AMOSTRA_POR_CATEGORIA = 50
SEED = 42
DIR_REP = F.RAIZ / "reports"
ARQ_BASELINE_NLI = DIR_REP / "nlp_predicoes_baseline_nli.csv"
ARQ_INDEPENDENTE = F.RAIZ / "tests" / "dados" / "avaliacao_independente_nlp.csv"
ORDEM = [str(c) for c in Categoria]


def avaliar_guardrail() -> dict:
    lotes = pd.read_csv(F.ARQUIVO_LOTES, usecols=["descricao_texto", "texto_adversarial"], low_memory=False)
    resultado = {}
    for nome, mod in (("v1", guardrail_v1), (guardrails.VERSAO, guardrails)):
        bloq = lotes["descricao_texto"].map(lambda t: mod.filtrar_entrada(t).bloqueado)
        adv = lotes["texto_adversarial"]
        resultado[nome] = {
            "dataset_adversariais_bloqueados": f"{int(bloq[adv].sum())}/{int(adv.sum())}",
            "dataset_falsos_positivos": f"{int(bloq[~adv].sum())}/{int((~adv).sum())}",
            "ineditos_A_bloqueados": f"{sum(mod.filtrar_entrada(t).bloqueado for t in CONJUNTO_A)}/{len(CONJUNTO_A)}",
            "ineditos_B_bloqueados": f"{sum(mod.filtrar_entrada(t).bloqueado for t in CONJUNTO_B)}/{len(CONJUNTO_B)}",
            "benignos_falsos_positivos": f"{sum(mod.filtrar_entrada(t).bloqueado for t in BENIGNOS_SUSPEITOS)}/{len(BENIGNOS_SUSPEITOS)}",
        }
    resultado["passaram_no_B_" + guardrails.VERSAO] = [t for t in CONJUNTO_B if not guardrails.filtrar_entrada(t).bloqueado]
    return resultado


def _metricas(df: pd.DataFrame, col_pred: str, col_arm: str, segundos: float | None) -> dict:
    fria = df[df["categoria"].isin([str(c) for c in CADEIA_FRIA])]
    return {
        "amostra": len(df),
        "acuracia_categoria": round(accuracy_score(df["categoria"], df[col_pred]), 4),
        "acuracia_por_categoria": df.assign(ok=df[col_pred] == df["categoria"]).groupby("categoria")["ok"].mean().round(3).to_dict(),
        "acuracia_armazenamento_cadeia_fria": round(accuracy_score(fria["armazenamento"], fria[col_arm]), 4) if len(fria) else None,
        "segundos_por_texto": round(segundos / len(df), 4) if segundos else None,
        "matriz_confusao": {"ordem": ORDEM, "valores": confusion_matrix(df["categoria"], df[col_pred], labels=ORDEM).tolist()},
        "exemplos_de_erro": df.loc[df[col_pred] != df["categoria"], ["descricao_texto", "categoria", col_pred]]
        .head(8).rename(columns={col_pred: "previsto"}).to_dict("records"),
    }


def _prever(clf, textos: list[str]) -> tuple[list[str], list[str], float]:
    inicio = time.perf_counter()
    sugestoes = clf.sugerir_lote(textos)
    return ([str(s.categoria) if s.categoria else None for s in sugestoes],
            [str(s.armazenamento) if s.armazenamento else None for s in sugestoes],
            time.perf_counter() - inicio)


def ler_conjunto_independente() -> pd.DataFrame:
    """Aceita CSV salvo pelo VS Code/Bloco de Notas (vírgula, UTF-8) ou pelo Excel (ponto e vírgula, Windows-1252)."""
    if not ARQ_INDEPENDENTE.exists():
        return pd.DataFrame()
    for codificacao in ("utf-8-sig", "cp1252"):
        try:
            df = pd.read_csv(ARQ_INDEPENDENTE, sep=None, engine="python", encoding=codificacao)
            break
        except UnicodeDecodeError:
            continue
    df.columns = [c.strip().lower() for c in df.columns]
    df = df.dropna(subset=["descricao", "categoria"])
    df["categoria"] = df["categoria"].str.strip().str.lower()
    df["armazenamento"] = df["armazenamento"].fillna("ambiente").str.strip().str.lower()
    return df


def amostra_teste() -> pd.DataFrame:
    _, _, teste = F.split_temporal(F.carregar_lotes_validos())
    teste = teste[~teste["texto_adversarial"]]
    return teste.groupby("categoria").sample(n=AMOSTRA_POR_CATEGORIA, random_state=SEED).reset_index(drop=True)


def main(com_nli: bool = False) -> None:
    amostra = amostra_teste()
    sim = ClassificadorSimilaridade()
    amostra["cat_sim"], amostra["arm_sim"], seg_sim = _prever(sim, amostra["descricao_texto"].tolist())

    if com_nli or not ARQ_BASELINE_NLI.exists():
        nli = ClassificadorZeroShotNLI()
        amostra["cat_nli"], amostra["arm_nli"], seg_nli = _prever(nli, amostra["descricao_texto"].tolist())
        amostra[["lote_id", "descricao_texto", "categoria", "armazenamento", "cat_nli", "arm_nli"]].rename(
            columns={"cat_nli": "cat_prevista", "arm_nli": "arm_previsto"}).to_csv(ARQ_BASELINE_NLI, index=False)
    else:
        base = pd.read_csv(ARQ_BASELINE_NLI).set_index("lote_id")
        amostra["cat_nli"] = amostra["lote_id"].map(base["cat_prevista"])
        amostra["arm_nli"] = amostra["lote_id"].map(base["arm_previsto"])
        seg_nli = None
        assert amostra["cat_nli"].notna().all(), "amostra do baseline não confere: rode com --com-nli"

    relatorio = {
        "guardrail": avaliar_guardrail(),
        "classificador_padrao": {"tipo": "similaridade (embeddings + exemplos)", "modelo": MODELO_EMBEDDINGS,
                                 "revisao": REVISAO_EMBEDDINGS,
                                 "teste_dataset": _metricas(amostra, "cat_sim", "arm_sim", seg_sim)},
        "baseline_nli": {"tipo": "zero-shot NLI", "modelo": MODELO_NLI, "revisao": REVISAO_NLI,
                         "teste_dataset": _metricas(amostra, "cat_nli", "arm_nli", seg_nli)
                         | ({} if seg_nli else {"segundos_por_texto": 3.337})},
    }

    indep = ler_conjunto_independente()
    if len(indep):
        indep = indep.rename(columns={"descricao": "descricao_texto"})
        invalidas = set(indep["categoria"]) - set(ORDEM)
        if invalidas:
            raise ValueError(f"Categorias inválidas no conjunto independente: {invalidas}")
        indep["cat_sim"], indep["arm_sim"], seg = _prever(sim, indep["descricao_texto"].tolist())
        relatorio["classificador_padrao"]["independente"] = _metricas(indep, "cat_sim", "arm_sim", seg)
    else:
        relatorio["classificador_padrao"]["independente"] = "pendente: preencher tests/dados/avaliacao_independente_nlp.csv"

    amostra[["lote_id", "descricao_texto", "categoria", "armazenamento", "cat_sim", "arm_sim"]].to_csv(
        DIR_REP / "nlp_predicoes_similaridade.csv", index=False)
    (DIR_REP / "avaliacao_nlp.json").write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    resumo = {k: (v if k == "guardrail" else {kk: vv for kk, vv in v.items() if kk not in ("teste_dataset",)}
                  | {"teste": {m: v["teste_dataset"][m] for m in ("acuracia_categoria", "acuracia_por_categoria",
                                                                  "acuracia_armazenamento_cadeia_fria", "segundos_por_texto")}})
              for k, v in relatorio.items()}
    print(json.dumps(resumo, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main(com_nli="--com-nli" in sys.argv)

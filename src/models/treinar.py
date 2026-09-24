"""Treino e avaliação do Modelo 1 (prioridade) e do Modelo 2 (risco de descarte).

Metodologia (regras, seções 5 e 8):
- split temporal: ajuste (set/25-fev/26) -> validação (mar-mai/26) -> teste (jun-ago/26);
- baselines: classificador ingênuo + a regra/heurística atual; candidatos: Regressão
  Logística, Random Forest e HistGradientBoosting;
- seleção de modelo e do threshold do M2 na VALIDAÇÃO; o teste só é usado uma vez, no final;
- no teste, o M2 recebe a prioridade PREVISTA pelo M1 (encadeamento real), não o rótulo.

Uso:
    python -m src.models.treinar
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from src.data import parametros as P
from src.data.curadoria_ipvs import RAIZ
from src.models import features as F
from src.regras.dominio import ORDEM_PRIORIDADE

DIR_MODELOS = RAIZ / "models"
DIR_RELATORIOS = RAIZ / "reports"
RECALL_ALVO_M2 = 0.85
SEED = P.SEED


def _pipeline(estimador, categoricas, numericas, booleanas, escalar: bool) -> Pipeline:
    etapas_num = [("imputar", SimpleImputer(strategy="median", add_indicator=True))]
    if escalar:
        etapas_num.append(("escalar", StandardScaler()))
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), categoricas),
        ("num", Pipeline(etapas_num), numericas),
        ("bool", "passthrough", booleanas),
    ])
    return Pipeline([("pre", pre), ("modelo", estimador)])


def _candidatos(categoricas, numericas, booleanas) -> dict[str, Pipeline]:
    return {
        "regressao_logistica": _pipeline(
            LogisticRegression(max_iter=3000, class_weight="balanced"), categoricas, numericas, booleanas, escalar=True
        ),
        "random_forest": _pipeline(
            RandomForestClassifier(n_estimators=300, min_samples_leaf=5, class_weight="balanced_subsample",
                                   n_jobs=-1, random_state=SEED),
            categoricas, numericas, booleanas, escalar=False,
        ),
        "hist_gradient_boosting": _pipeline(
            HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, class_weight="balanced", random_state=SEED),
            categoricas, numericas, booleanas, escalar=False,
        ),
    }


def _sha256(caminho) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _salvar_modelo(nome: str, pipeline: Pipeline, metadados: dict) -> None:
    """Salva o modelo + metadados de rastreabilidade (versão, dados, hash do artefato).

    O hash permite verificar a integridade antes de carregar: um .joblib adulterado
    pode executar código arbitrário ao ser desserializado.
    """
    DIR_MODELOS.mkdir(exist_ok=True)
    caminho = DIR_MODELOS / f"{nome}.joblib"
    joblib.dump(pipeline, caminho)
    metadados |= {"artefato": caminho.name, "sha256_artefato": _sha256(caminho)}
    (DIR_MODELOS / f"{nome}.json").write_text(json.dumps(metadados, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


# --- Modelo 1 -------------------------------------------------------------------------------------
def _metricas_m1(y_true, y_pred) -> dict:
    return {
        "acuracia": round(accuracy_score(y_true, y_pred), 4),
        "f1_macro": round(f1_score(y_true, y_pred, average="macro"), 4),
        "recall_critica": round(recall_score(y_true, y_pred, labels=["CRITICA"], average="macro"), 4),
    }


def treinar_m1(ajuste, validacao, teste) -> tuple[Pipeline, dict]:
    cols = F.M1_CATEGORICAS + F.M1_NUMERICAS + F.M1_BOOLEANAS
    F.checar_vazamento(cols)
    y = F.M1_ALVO
    resultados = {"baselines": {}, "validacao": {}, "teste": {}}

    ingenuo = DummyClassifier(strategy="most_frequent").fit(ajuste[cols], ajuste[y])
    resultados["baselines"]["ingenuo_validacao"] = _metricas_m1(validacao[y], ingenuo.predict(validacao[cols]))
    resultados["baselines"]["regra_validacao"] = _metricas_m1(validacao[y], validacao["prioridade_regra"])

    candidatos = _candidatos(F.M1_CATEGORICAS, F.M1_NUMERICAS, F.M1_BOOLEANAS)
    for nome, pipe in candidatos.items():
        pipe.fit(ajuste[cols], ajuste[y])
        resultados["validacao"][nome] = _metricas_m1(validacao[y], pipe.predict(validacao[cols]))
    melhor = max(resultados["validacao"], key=lambda n: resultados["validacao"][n]["f1_macro"])

    treino = pd.concat([ajuste, validacao])
    final = _candidatos(F.M1_CATEGORICAS, F.M1_NUMERICAS, F.M1_BOOLEANAS)[melhor].fit(treino[cols], treino[y])
    pred = final.predict(teste[cols])
    resultados["teste"] = {
        "modelo": melhor,
        **_metricas_m1(teste[y], pred),
        "regra_no_teste": _metricas_m1(teste[y], teste["prioridade_regra"]),
        "ingenuo_no_teste": _metricas_m1(teste[y], ingenuo.predict(teste[cols])),
        "matriz_confusao": {
            "ordem": [str(p) for p in ORDEM_PRIORIDADE],
            "valores": confusion_matrix(teste[y], pred, labels=[str(p) for p in ORDEM_PRIORIDADE]).tolist(),
        },
    }
    return final, resultados


# --- Modelo 2 -------------------------------------------------------------------------------------
def _metricas_m2(y_true, proba, limiar) -> dict:
    pred = proba >= limiar
    return {
        "acuracia": round(accuracy_score(y_true, pred), 4),
        "precisao": round(precision_score(y_true, pred, zero_division=0), 4),
        "recall": round(recall_score(y_true, pred), 4),
        "f1": round(f1_score(y_true, pred), 4),
        "roc_auc": round(roc_auc_score(y_true, proba), 4) if len(set(proba)) > 1 else None,
        "pr_auc": round(average_precision_score(y_true, proba), 4),
    }


def _limiar_para_recall(y_true, proba, recall_alvo: float) -> float:
    """Maior limiar (logo, maior precisão) que ainda garante o recall-alvo."""
    precisao, recall, limiares = precision_recall_curve(y_true, proba)
    ok = np.flatnonzero(recall[:-1] >= recall_alvo)
    return float(limiares[ok[-1]]) if len(ok) else float(limiares[0])


def _heuristica_v0(df: pd.DataFrame) -> np.ndarray:
    """Heurística operacional pré-IA: risco alto se faltam < 4 h para o limite de consumo."""
    margem = df["categoria"].map({str(k): v for k, v in P.MARGEM_CONSUMO_HORAS.items()})
    return ((df["horas_restantes"] - margem) < P.HEURISTICA_RISCO_HORAS).astype(float).to_numpy()


def treinar_m2(ajuste, validacao, teste, m1_ajuste: Pipeline, m1_final: Pipeline) -> tuple[Pipeline, dict]:
    cols = F.M2_CATEGORICAS + F.M2_NUMERICAS + F.M2_BOOLEANAS
    F.checar_vazamento(cols)
    y = F.M2_ALVO
    m1_cols = F.M1_CATEGORICAS + F.M1_NUMERICAS + F.M1_BOOLEANAS

    # Validação e teste recebem a prioridade PREVISTA pelo M1 (como em produção).
    validacao = validacao.assign(prioridade=m1_ajuste.predict(validacao[m1_cols]))
    teste = teste.assign(prioridade=m1_final.predict(teste[m1_cols]))

    resultados = {"baselines": {}, "validacao": {}, "teste": {}}
    resultados["baselines"]["ingenuo_validacao"] = _metricas_m2(validacao[y], np.zeros(len(validacao)), 0.5)
    resultados["baselines"]["heuristica_v0_validacao"] = _metricas_m2(validacao[y], _heuristica_v0(validacao), 0.5)

    probas_val = {}
    for nome, pipe in _candidatos(F.M2_CATEGORICAS, F.M2_NUMERICAS, F.M2_BOOLEANAS).items():
        pipe.fit(ajuste[cols], ajuste[y])
        probas_val[nome] = pipe.predict_proba(validacao[cols])[:, 1]
        limiar = _limiar_para_recall(validacao[y], probas_val[nome], RECALL_ALVO_M2)
        resultados["validacao"][nome] = {"limiar": round(limiar, 4), **_metricas_m2(validacao[y], probas_val[nome], limiar)}
    melhor = max(resultados["validacao"], key=lambda n: resultados["validacao"][n]["pr_auc"])
    limiar = resultados["validacao"][melhor]["limiar"]

    treino = pd.concat([ajuste, validacao])
    final = _candidatos(F.M2_CATEGORICAS, F.M2_NUMERICAS, F.M2_BOOLEANAS)[melhor].fit(treino[cols], treino[y])
    proba = final.predict_proba(teste[cols])[:, 1]
    pred = proba >= limiar
    resultados["teste"] = {
        "modelo": melhor,
        "limiar": limiar,
        **_metricas_m2(teste[y], proba, limiar),
        "heuristica_v0_no_teste": _metricas_m2(teste[y], _heuristica_v0(teste), 0.5),
        "ingenuo_no_teste": _metricas_m2(teste[y], np.zeros(len(teste)), 0.5),
        "taxa_descarte_teste": round(float(teste[y].mean()), 4),
        "matriz_confusao": {"ordem": ["salvo", "descartado"], "valores": confusion_matrix(teste[y], pred).tolist()},
    }

    amostra = teste.sample(min(4000, len(teste)), random_state=SEED)
    imp = permutation_importance(final, amostra[cols], amostra[y], scoring="average_precision",
                                 n_repeats=5, random_state=SEED, n_jobs=-1)
    resultados["importancia_permutacao"] = dict(
        sorted(((c, round(float(v), 4)) for c, v in zip(cols, imp.importances_mean)), key=lambda kv: -kv[1])
    )
    return final, resultados


def main() -> None:
    lotes = F.carregar_lotes_validos()
    ajuste, validacao, teste = F.split_temporal(lotes)
    print(f"ajuste={len(ajuste):,} | validação={len(validacao):,} | teste={len(teste):,}")

    m1_cols = F.M1_CATEGORICAS + F.M1_NUMERICAS + F.M1_BOOLEANAS
    m1_final, res_m1 = treinar_m1(ajuste, validacao, teste)
    m1_ajuste = _candidatos(F.M1_CATEGORICAS, F.M1_NUMERICAS, F.M1_BOOLEANAS)[res_m1["teste"]["modelo"]]
    m1_ajuste.fit(ajuste[m1_cols], ajuste[F.M1_ALVO])
    m2_final, res_m2 = treinar_m2(ajuste, validacao, teste, m1_ajuste, m1_final)

    comum = {
        "treinado_em": datetime.now().isoformat(timespec="seconds"),
        "sklearn": sklearn.__version__,
        "dataset": F.ARQUIVO_LOTES.name,
        "sha256_dataset": _sha256(F.ARQUIVO_LOTES),
        "split": {"inicio_validacao": F.INICIO_VALIDACAO, "inicio_teste": F.INICIO_TESTE},
    }
    _salvar_modelo("modelo_prioridade", m1_final, comum | {
        "versao": "prioridade-v1", "features": m1_cols, "metricas_teste": res_m1["teste"]})
    _salvar_modelo("modelo_descarte", m2_final, comum | {
        "versao": "descarte-v1", "features": F.M2_CATEGORICAS + F.M2_NUMERICAS + F.M2_BOOLEANAS,
        "limiar": res_m2["teste"]["limiar"], "metricas_teste": res_m2["teste"]})

    DIR_RELATORIOS.mkdir(exist_ok=True)
    relatorio = {"modelo_1_prioridade": res_m1, "modelo_2_descarte": res_m2, **comum}
    (DIR_RELATORIOS / "metricas_modelos.json").write_text(
        json.dumps(relatorio, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({"M1_teste": res_m1["teste"], "M2_teste": res_m2["teste"],
                      "M2_importancia": res_m2["importancia_permutacao"]}, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()

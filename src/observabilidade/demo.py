"""Demonstração da observabilidade sobre o ano simulado (regras 10.2).

Duas perguntas honestas:
1. Em dados NORMAIS, quantos alertas a linha de base gera? (fadiga de alertas)
2. Anomalias INJETADAS no fim do ano são detectadas, e em que nível?

Também mede o drift (PSI) entre o período de treino e o de teste dos modelos.

Uso:
    python -m src.observabilidade.demo
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

import pandas as pd

from src.data.curadoria_ipvs import RAIZ
from src.models import features as F
from src.observabilidade.anomalias import Monitor, Nivel
from src.observabilidade.drift import relatorio_drift
from src.observabilidade.freio import Freio

DIR = RAIZ / "data" / "processed"
SAIDA = RAIZ / "reports" / "observabilidade_demo.json"


def _replay(monitor: Monitor, lotes: pd.DataFrame, eventos: pd.DataFrame) -> dict:
    """Alimenta o monitor com o ano normal, em ordem cronológica, e conta os alertas."""
    lotes = lotes.sort_values("ts_cadastro")
    dias = pd.date_range(lotes["ts_cadastro"].min().normalize(), lotes["ts_cadastro"].max().normalize(), freq="D")
    por_dia = lotes.groupby([lotes["ts_cadastro"].dt.normalize(), "doador_id"]).size()
    recusas = eventos[eventos["tipo"] == "RECUSA_ONG"]
    recusas_dia = recusas.groupby([recusas["ts"].dt.normalize(), "ator"]).size()
    caixa = lotes[lotes["caixa_aprovado"] == True]  # noqa: E712
    caixa_dia = caixa.groupby([caixa["ts_cadastro"].dt.normalize(), "ong_id"])["custo_caixa"].sum()

    antes = len(monitor.alertas)
    medicoes = Counter()
    doadores = lotes["doador_id"].unique()
    for dia in dias:
        for d in doadores:  # dias sem doação também entram (o normal de muitos doadores é 0)
            monitor.medir("cadastros_por_dia", d, dia.to_pydatetime(), float(por_dia.get((dia, d), 0)))
            medicoes["cadastros_por_dia"] += 1
    for (dia, ator), n in recusas_dia.items():
        monitor.medir("recusas_por_dia", ator, dia.to_pydatetime(), float(n))
        medicoes["recusas_por_dia"] += 1
    for (dia, ong), valor in caixa_dia.items():
        monitor.medir("gasto_caixa_dia", ong, dia.to_pydatetime(), float(valor))
        medicoes["gasto_caixa_dia"] += 1
    for lote in lotes.itertuples():
        monitor.medir("peso_lote", lote.doador_id, lote.ts_cadastro.to_pydatetime(), float(lote.peso_kg))
        medicoes["peso_lote"] += 1

    alertas = monitor.alertas[antes:]
    por_sinal = {}
    for sinal, n in medicoes.items():
        niveis = Counter(a.nivel.name for a in alertas if a.sinal == sinal)
        por_sinal[sinal] = {"medicoes": n, "alertas": dict(niveis),
                            "taxa_alerta_ou_mais": round(sum(1 for a in alertas if a.sinal == sinal
                                                             and a.nivel >= Nivel.ALERTA) / n, 5)}
    return por_sinal


def _injetar(monitor: Monitor, freio: Freio, fim: datetime, lotes: pd.DataFrame) -> list[dict]:
    """Anomalias plantadas depois do ano normal. Cada uma registra o nível detectado."""
    resultados = []
    doador = lotes["doador_id"].value_counts().index[50]  # doador comum, com histórico
    peso_normal = float(lotes.loc[lotes["doador_id"] == doador, "peso_kg"].median())
    dia = fim + timedelta(days=1)
    for nome, sinal, chave, valor in [
        ("doador cadastra 25 lotes num dia", "cadastros_por_dia", doador, 25.0),
        # O peso simulado varia muito (lognormal): 10x ainda pode ser natural; 50x não.
        ("lote 10x mais pesado que o normal do doador", "peso_lote", doador, peso_normal * 10),
        ("lote 50x mais pesado que o normal do doador", "peso_lote", doador, peso_normal * 50),
        ("ONG chega a R$ 185 de caixa no dia", "gasto_caixa_dia", "O-001", 185.0),
    ]:
        a = monitor.medir(sinal, chave, dia, valor, aprender=False)
        resultados.append({"anomalia": nome, "sinal": sinal, "detectado": a is not None,
                           "nivel": a.nivel.name if a else "NORMAL", "motivo": a.avaliacao.motivo if a else ""})

    # Rajada: 5 requisições/min normais por 30 min, depois 200 em um minuto.
    ip = "ip:demo"
    t0 = dia.replace(hour=10)
    for minuto in range(30):
        for s in range(5):
            monitor.contar("requisicoes_por_minuto", ip, t0 + timedelta(minutes=minuto, seconds=10 * s))
    rajada = t0 + timedelta(minutes=40)
    niveis = [monitor.contar("requisicoes_por_minuto", ip, rajada + timedelta(milliseconds=250 * i)) for i in range(200)]
    primeiro = next((i for i, a in enumerate(niveis) if a and a.nivel >= Nivel.ALERTA), None)
    resultados.append({"anomalia": "rajada de 200 requisições em 1 minuto", "sinal": "requisicoes_por_minuto",
                       "detectado": primeiro is not None, "nivel": "ALERTA" if primeiro is not None else "NORMAL",
                       "detectado_na_requisicao": None if primeiro is None else primeiro + 1,
                       "freio_aplicado": freio.ativo(ip, rajada + timedelta(seconds=55)) is not None})
    return resultados


def main() -> None:
    lotes = pd.read_csv(DIR / "lotes.csv", parse_dates=["ts_cadastro"], low_memory=False)
    eventos = pd.read_csv(DIR / "eventos.csv.gz", parse_dates=["ts"])
    freio = Freio()
    monitor = Monitor(freio=freio)

    normal = _replay(monitor, lotes, eventos)
    injetadas = _injetar(monitor, freio, lotes["ts_cadastro"].max().to_pydatetime(), lotes)

    validos = F.carregar_lotes_validos()
    ajuste, _, teste = F.split_temporal(validos)
    drift = relatorio_drift(ajuste, teste, ["horas_restantes", "peso_kg", "dist_ong_top_km", "min_ate_receber_top"],
                            ["categoria", "prioridade", "regiao"])

    relatorio = {"dados_normais": normal, "anomalias_injetadas": injetadas,
                 "drift_treino_vs_teste": drift, "gerado_em": datetime.now().isoformat(timespec="seconds")}
    SAIDA.parent.mkdir(exist_ok=True)
    SAIDA.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(relatorio, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

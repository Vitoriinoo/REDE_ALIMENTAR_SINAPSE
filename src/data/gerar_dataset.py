"""Gera o dataset simulado da Rede Alimenta IA (reprodutível pela SEED).

Pré-requisito: `python -m src.data.curadoria_ipvs` (gera data/reference/).

Uso:
    python -m src.data.gerar_dataset
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from src.data import parametros as P
from src.data.curadoria_ipvs import RAIZ
from src.data.entidades import (
    carregar_regioes,
    carregar_setores,
    gerar_doadores,
    gerar_hubs,
    gerar_ongs,
    gerar_transportadores,
)
from src.data.simulacao import Simulador
from src.regras.dominio import Categoria
from src.regras.logistica import PEDIDOS_ABERTOS_MAXIMO

DIR_SAIDA = RAIZ / "data" / "processed"


def gerar_contexto_diario(rng: np.random.Generator) -> pd.DataFrame:
    dias = pd.date_range(P.INICIO, P.FIM + timedelta(days=P.DIAS_FOLGA), freq="D")
    feriados = set(pd.to_datetime(P.FERIADOS).date)
    ctx = pd.DataFrame({"data": dias.date})
    ctx["dia_semana"] = dias.weekday
    ctx["mes"] = dias.month
    ctx["feriado"] = ctx["data"].isin(feriados)
    ctx["chuva"] = rng.random(len(ctx)) < ctx["mes"].map(P.PROB_CHUVA_MES)  # latente
    ctx["no_periodo"] = ctx["data"] <= P.FIM
    return ctx


def _sortear_hora(rng: np.random.Generator, segmento: str) -> float:
    ini, fim = P.FUNCIONAMENTO[segmento]
    if rng.random() < P.FRACAO_NOS_PICOS:
        picos = P.PICOS_HORARIO[segmento]
        pesos = np.array([p[2] for p in picos])
        centro, desvio, _ = picos[rng.choice(len(picos), p=pesos / pesos.sum())]
        return float(np.clip(rng.normal(centro, desvio), ini, fim - 1 / 60))
    return float(rng.uniform(ini, fim))


def gerar_cadastros(rng: np.random.Generator, doadores: pd.DataFrame, ctx: pd.DataFrame) -> list[tuple]:
    """(timestamp, doador, categoria) de todas as doações do período, em ordem cronológica."""
    cadastros = []
    for dia in ctx[ctx["no_periodo"]].itertuples():
        meia_noite = datetime.combine(dia.data, datetime.min.time())
        mult_dia = P.MULT_MES.get(dia.mes, 1.0) * (P.MULT_FERIADO if dia.feriado else 1.0)
        for d in doadores.itertuples():
            taxa = P.DOACOES_POR_SEMANA[d.segmento] / 7 * P.MULT_DIA_SEMANA[d.segmento][dia.dia_semana]
            n = rng.poisson(taxa * mult_dia * d.fator_frequencia)
            mix = P.MIX_CATEGORIAS[d.segmento]
            for _ in range(n):
                hora = _sortear_hora(rng, d.segmento)
                categoria = Categoria(rng.choice(list(mix), p=np.array(list(mix.values())) / sum(mix.values())))
                ts = (meia_noite + timedelta(hours=hora)).replace(second=0, microsecond=0)
                cadastros.append((ts, d, categoria))
    cadastros.sort(key=lambda c: c[0])
    return cadastros


def gerar_pedidos(rng: np.random.Generator, ongs: pd.DataFrame, ctx: pd.DataFrame) -> pd.DataFrame:
    """Pedidos de alimentos abertos pelas ONGs aprovadas (regras 6.5): ~0,5 por semana por ONG,
    categoria entre as que a ONG aceita, kg <= capacidade diária, validade de 3 a 7 dias."""
    pedidos = []
    aprovadas = ongs[ongs["status_aprovacao"] == "aprovada"]
    for dia in ctx[ctx["no_periodo"]]["data"]:
        meia_noite = datetime.combine(dia, datetime.min.time())
        for ong in aprovadas.itertuples():
            if rng.random() >= P.PEDIDOS_POR_SEMANA_POR_ONG / 7:
                continue
            aceitas = [Categoria(c) for c in ong.categorias_aceitas.split("|")]
            pesos = np.array([P.PEDIDO_PESO_CATEGORIA[c] for c in aceitas])
            categoria = aceitas[rng.choice(len(aceitas), p=pesos / pesos.sum())]
            abertura = meia_noite + timedelta(hours=float(rng.uniform(ong.abertura_h, ong.fechamento_h)))
            abertos = sum(1 for p in pedidos if p["ong_id"] == ong.ong_id and p["ts_expira"] > abertura)
            if abertos >= PEDIDOS_ABERTOS_MAXIMO:  # regra 6.5: no máximo 3 abertos
                continue
            pedidos.append({
                "ong_id": ong.ong_id, "categoria": str(categoria),
                "kg": round(float(ong.capacidade_kg_dia * rng.uniform(*P.PEDIDO_FRACAO_CAPACIDADE)), 1),
                "ts_abertura": abertura.replace(second=0, microsecond=0),
                "ts_expira": (abertura + timedelta(days=int(rng.integers(P.PEDIDO_VALIDADE_DIAS[0],
                                                                        P.PEDIDO_VALIDADE_DIAS[1] + 1)))
                              ).replace(second=0, microsecond=0),
            })
    df = pd.DataFrame(pedidos).sort_values("ts_abertura").reset_index(drop=True)
    df.insert(0, "pedido_id", [f"P-{i:05d}" for i in range(1, len(df) + 1)])
    return df


def main() -> None:
    rng = np.random.default_rng(P.SEED)
    setores, regioes = carregar_setores(), carregar_regioes()

    doadores = gerar_doadores(rng, setores)
    ongs = gerar_ongs(rng, setores)
    hubs = gerar_hubs(rng, setores)
    transportadores = gerar_transportadores(rng, setores, regioes)
    ctx = gerar_contexto_diario(rng)
    pedidos = gerar_pedidos(rng, ongs, ctx)

    sim = Simulador(rng, doadores, ongs, hubs, transportadores, ctx, pedidos)
    cadastros = gerar_cadastros(rng, doadores, ctx)
    lotes = pd.DataFrame(
        [sim.simular_lote(f"L-{i:06d}", d, cat, ts) for i, (ts, d, cat) in enumerate(cadastros, start=1)]
    )
    eventos = pd.DataFrame(sim.eventos).sort_values(["ts", "lote_id"], kind="stable").reset_index(drop=True)
    eventos.insert(0, "evento_id", [f"E-{i:07d}" for i in range(1, len(eventos) + 1)])

    DIR_SAIDA.mkdir(parents=True, exist_ok=True)
    doadores.drop(columns=["fator_frequencia"]).to_csv(DIR_SAIDA / "doadores.csv", index=False)
    ongs.to_csv(DIR_SAIDA / "ongs.csv", index=False)
    hubs.to_csv(DIR_SAIDA / "hubs.csv", index=False)
    transportadores.to_csv(DIR_SAIDA / "transportadores.csv", index=False)
    ctx[ctx["no_periodo"]].drop(columns="no_periodo").to_csv(DIR_SAIDA / "contexto_diario.csv", index=False)
    lotes.to_csv(DIR_SAIDA / "lotes.csv", index=False)
    eventos.to_csv(DIR_SAIDA / "eventos.csv.gz", index=False, compression="gzip")
    restante = sim.kg_restante_por_pedido()
    pedidos["kg_atendido"] = (pedidos["kg"] - pedidos["pedido_id"].map(restante)).round(1)
    pedidos["status"] = np.where(pedidos["kg_atendido"] >= pedidos["kg"], "atendido",
                                 np.where(pedidos["kg_atendido"] > 0, "parcial", "expirado"))
    pedidos.to_csv(DIR_SAIDA / "pedidos.csv", index=False)

    resumo(lotes, eventos)


def resumo(lotes: pd.DataFrame, eventos: pd.DataFrame) -> None:
    validos = lotes[lotes["status_final"] != "BLOQUEADO"]
    bloq = lotes[lotes["status_final"] == "BLOQUEADO"]
    print(f"Lotes cadastrados: {len(lotes):,} | bloqueados: {len(bloq) / len(lotes):.1%} "
          f"(questionário {(bloq['motivo_descarte'] == 'QUESTIONARIO').sum():,}, "
          f"validade {(bloq['motivo_descarte'] == 'VALIDADE_ABAIXO_DO_MINIMO').sum():,})")
    print(f"Lotes válidos: {len(validos):,} | eventos: {len(eventos):,}")
    print(f"Taxa de descarte: {validos['descartado'].mean():.1%}")
    print("\nMotivos de descarte:\n", validos["motivo_descarte"].value_counts(normalize=True).round(3).to_string())
    print("\nPrioridade (rótulo):\n", validos["prioridade"].value_counts(normalize=True).round(3).to_string())
    print("\nDescarte por prioridade:\n", validos.groupby("prioridade")["descartado"].mean().round(3).to_string())
    print("\nModalidade:\n", validos["modalidade"].value_counts(normalize=True).round(3).to_string())
    entregues = validos[validos["status_final"] == "ENTREGUE"]
    print(f"\nkg salvos: {entregues['peso_kg'].sum():,.0f} | refeições: {entregues['refeicoes'].sum():,.0f}")
    print(f"Tempo mediano de match: {validos['minutos_ate_match'].median():.1f} min | pago acionado: {validos['acionou_pago'].mean():.1%}")
    print("\nComplementaridade (lotes com ONG):\n", validos["complementaridade"].value_counts(normalize=True).round(3).to_string())
    print(f"ONG escolhida tinha pedido aberto: {validos['ong_tinha_pedido'].dropna().astype(bool).mean():.1%}")


if __name__ == "__main__":
    main()

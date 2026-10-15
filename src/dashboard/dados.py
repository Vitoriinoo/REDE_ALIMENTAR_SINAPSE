"""Dados do dashboard: visões agregadas do Supabase ou, sem banco, o dataset simulado.

Com `REDE_ALIMENTA_DASHBOARD_DB_URL`, o dashboard conecta com o papel `rede_dashboard`, que só
enxerga as visões `rede.vw_*` (db/schema.sql): agregados, sem identificador de pessoa. Sem a
variável, calcula os mesmos agregados a partir de `data/processed/` (mesma forma de tabela).
"""

from __future__ import annotations

import json
import os

import pandas as pd

from src.data.curadoria_ipvs import RAIZ

DADOS = RAIZ / "data" / "processed"


def _segredo(nome: str) -> str | None:
    """Variável de ambiente (Docker) ou Secrets do Streamlit Community Cloud."""
    if os.environ.get(nome):
        return os.environ[nome]
    try:
        import streamlit as st

        return st.secrets.get(nome)
    except Exception:  # noqa: BLE001 - sem secrets.toml: modo arquivo
        return None


URL = _segredo("REDE_ALIMENTA_DASHBOARD_DB_URL")
# Endereço da API para as pessoas (links) e para o próprio servidor do dashboard (chamadas).
# No Compose eles diferem: o navegador usa localhost:8000, o container usa http://api:8000.
API_PUBLICA = (_segredo("REDE_ALIMENTA_API_PUBLICA") or "http://localhost:8000").rstrip("/")
API_INTERNA = (_segredo("REDE_ALIMENTA_API_URL") or API_PUBLICA).rstrip("/")


def fonte() -> str:
    return "Supabase (visões agregadas)" if URL else "Dataset simulado (arquivos)"


def _sql(consulta: str) -> pd.DataFrame:
    import psycopg

    with psycopg.connect(URL, connect_timeout=5) as c:
        cur = c.execute(consulta)
        cols = [d.name for d in cur.description]
        df = pd.DataFrame(cur.fetchall(), columns=cols)
    for col in df.columns:  # NUMERIC chega como Decimal
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col])
            except (ValueError, TypeError):
                pass
    return df


def _lotes() -> pd.DataFrame:
    l = pd.read_csv(DADOS / "lotes.csv", low_memory=False,
                    usecols=["lote_id", "doador_id", "regiao", "ts_cadastro", "categoria", "peso_kg", "prioridade",
                             "minutos_ate_match", "ong_id", "status_final", "refeicoes", "motivo_descarte",
                             "modo_logistico"])
    l["ts_cadastro"] = pd.to_datetime(l["ts_cadastro"])
    return l


def impacto_regiao() -> pd.DataFrame:
    if URL:
        return _sql("SELECT * FROM rede.vw_impacto_regiao")
    r = pd.read_csv(RAIZ / "data" / "reference" / "regioes.csv")
    l = _lotes()
    o = pd.read_csv(DADOS / "ongs.csv", usecols=["ong_id", "regiao"]).rename(columns={"regiao": "regiao_ong"})
    ent = l[l.status_final == "ENTREGUE"].merge(o, on="ong_id")  # destino: onde a comida chegou
    agg = pd.DataFrame({
        "lotes": l.groupby("regiao").size(),  # origem: região do doador
        "entregues": ent.groupby("regiao_ong").size(),
        "descartados": l[l.status_final == "DESCARTADO"].groupby("regiao").size(),
        "kg_salvos": ent.groupby("regiao_ong")["peso_kg"].sum(),
        "refeicoes": ent.groupby("regiao_ong")["refeicoes"].sum(),
    }).fillna(0).reset_index(names="regiao")
    return r[["regiao", "municipio", "lat", "lon", "indice_vulnerabilidade"]].merge(agg, on="regiao", how="left").fillna(0)


def mensal() -> pd.DataFrame:
    if URL:
        df = _sql("SELECT * FROM rede.vw_impacto_mensal ORDER BY mes")
        df["mes"] = pd.to_datetime(df["mes"])
        return df
    l = _lotes()
    l["mes"] = l["ts_cadastro"].dt.to_period("M").dt.to_timestamp()
    aceitos = l[l.status_final.isin(["ENTREGUE", "DESCARTADO"])]
    g = aceitos.groupby("mes")
    return pd.DataFrame({
        "lotes_aceitos": g.size(), "descartados": g.apply(lambda x: (x.status_final == "DESCARTADO").sum()),
        "kg_salvos": g.apply(lambda x: x.loc[x.status_final == "ENTREGUE", "peso_kg"].sum()),
        "refeicoes": g.apply(lambda x: x.loc[x.status_final == "ENTREGUE", "refeicoes"].sum()),
        "mediana_match_min": g["minutos_ate_match"].median(), "media_match_min": g["minutos_ate_match"].mean(),
    }).reset_index().assign(origem="simulacao")


def match_prioridade() -> pd.DataFrame:
    if URL:
        return _sql("SELECT * FROM rede.vw_match_prioridade")
    l = _lotes().dropna(subset=["minutos_ate_match"])
    g = l.groupby("prioridade")["minutos_ate_match"]
    return pd.DataFrame({"matches": g.size(), "mediana_min": g.median(), "media_min": g.mean()}).reset_index()


def match_geral() -> dict:
    """Mediana e média de todos os matches (cadastro → aceite da ONG): o KPI do painel e do README."""
    if URL:
        linha = _sql("SELECT * FROM rede.vw_match_geral").iloc[0]
    else:
        m = _lotes()["minutos_ate_match"].dropna()
        linha = {"matches": len(m), "mediana_min": m.median(), "media_min": m.mean()}
    return {k: float(linha[k]) if linha[k] is not None else 0.0 for k in ("matches", "mediana_min", "media_min")}


def calor() -> pd.DataFrame:
    if URL:
        return _sql("SELECT * FROM rede.vw_calor_entregas")
    l = _lotes()
    o = pd.read_csv(DADOS / "ongs.csv", usecols=["ong_id", "lat", "lon"])
    e = l[l.status_final == "ENTREGUE"].merge(o, on="ong_id")
    e["lat"], e["lon"] = e["lat"].round(2), e["lon"].round(2)
    return e.groupby(["lat", "lon"], as_index=False)[["peso_kg", "refeicoes"]].sum().rename(
        columns={"peso_kg": "kg_salvos"})


def recentes() -> pd.DataFrame:
    if URL:
        return _sql("SELECT * FROM rede.vw_lotes_recentes")
    return pd.DataFrame(columns=["codigo", "regiao", "categoria", "peso_kg", "prioridade", "status_final",
                                 "ts_cadastro"])


PRIORIDADE = {"CRITICA": "CRÍTICA", "ALTA": "ALTA", "MEDIA": "MÉDIA", "BAIXA": "BAIXA"}
# Alerta visual (enunciado: vermelho/amarelo para validade crítica): só lote ainda PENDENTE, pela
# prioridade do Modelo 1, que já carrega a validade (regras 5). Nenhum limite novo de horas.
ALERTA = {"CRITICA": "critico", "ALTA": "atencao"}


def alertas_ao_vivo(r: pd.DataFrame) -> tuple[pd.DataFrame, list[str | None], int, int]:
    """Tabela rotulada, o nível de alerta de cada linha (None = sem alerta) e as contagens."""
    pendente = r["status_final"] == "PENDENTE"
    niveis = [ALERTA.get(p) if pend else None for p, pend in zip(r["prioridade"], pendente)]
    tabela = r.assign(prioridade=r["prioridade"].map(lambda p: PRIORIDADE.get(p, p)))
    for col in ("peso_kg", "risco_descarte"):  # NUMERIC chega como Decimal e aparece "9.500000"
        if col in tabela:
            tabela[col] = pd.to_numeric(tabela[col], errors="coerce").astype(float).round(2)
    return tabela, niveis, niveis.count("critico"), niveis.count("atencao")


def relatorio(nome: str) -> dict | None:
    caminho = RAIZ / "reports" / nome
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None

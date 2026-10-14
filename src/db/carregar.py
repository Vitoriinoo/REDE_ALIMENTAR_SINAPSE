"""Aplica db/schema.sql e carrega o ano simulado no Supabase (ou em qualquer PostgreSQL).

Roda UMA vez, pela pessoa administradora, com a conexão de dono do banco (papel `postgres`).
A API e o dashboard usam outros papéis, com menos privilégio (rede_api, rede_dashboard).
Idempotente: reaplica o esquema e insere só o que ainda não existe (ON CONFLICT DO NOTHING).

Uso:
    set REDE_ALIMENTA_DB_ADMIN_URL=postgresql://postgres.<projeto>:<senha>@<host>:5432/postgres
    python -m src.db.carregar [--com-eventos]
"""

from __future__ import annotations

import os
import sys
from datetime import timedelta, timezone

import pandas as pd

from src.data.curadoria_ipvs import RAIZ

DADOS = RAIZ / "data" / "processed"
BRASILIA = timezone(timedelta(hours=-3))


def _ts(serie: pd.Series) -> pd.Series:
    """Horário de Brasília sem fuso (dataset) -> TIMESTAMPTZ."""
    return pd.to_datetime(serie, format="mixed").dt.tz_localize(BRASILIA)


def tabelas(com_eventos: bool = False) -> dict[str, pd.DataFrame]:
    r = pd.read_csv(RAIZ / "data" / "reference" / "regioes.csv")
    d = pd.read_csv(DADOS / "doadores.csv").rename(columns={"doador_id": "codigo"})
    o = pd.read_csv(DADOS / "ongs.csv").rename(columns={"ong_id": "codigo"})
    o["turnos"] = o["turnos"].fillna("")
    h = pd.read_csv(DADOS / "hubs.csv").rename(columns={"hub_id": "codigo"})
    t = pd.read_csv(DADOS / "transportadores.csv").rename(columns={"transportador_id": "codigo"})
    p = pd.read_csv(DADOS / "pedidos.csv").rename(columns={"pedido_id": "codigo", "ong_id": "ong_codigo"})
    for c in ("ts_abertura", "ts_expira"):
        p[c] = _ts(p[c])

    l = pd.read_csv(DADOS / "lotes.csv", low_memory=False)
    lotes = pd.DataFrame({
        "codigo": l["lote_id"], "origem": "simulacao", "doador_codigo": l["doador_id"],
        "tipo_doador": l["tipo_doador"], "segmento": l["segmento"], "regiao": l["regiao"],
        "ts_cadastro": _ts(l["ts_cadastro"]), "categoria": l["categoria"], "armazenamento": l["armazenamento"],
        "peso_kg": l["peso_kg"].round(3), "validade_efetiva": _ts(l["validade_efetiva"]),
        "horas_restantes": l["horas_restantes"].round(2), "rota_expressa": l["rota_expressa"].astype(bool),
        "bloqueio": l["bloqueio_questionario"].where(l["bloqueio_questionario"].notna(),
                                                     l["motivo_descarte"].where(l["status_final"] == "BLOQUEADO")),
        "prioridade": l["prioridade"], "prioridade_fonte": l["prioridade"].where(l["prioridade"].isna(), "rotulo_triador"),
        "ong_codigo": l["ong_id"], "ts_aceite_ong": _ts(l["ts_aceite_ong"]),
        "minutos_ate_match": l["minutos_ate_match"].round(1), "modo_logistico": l["modo_logistico"],
        "excecao_redundante": l["excecao_redundante"].fillna(False).astype(bool), "modalidade": l["modalidade"],
        "acionou_pago": l["acionou_pago"].fillna(False).astype(bool), "status_final": l["status_final"],
        "motivo_descarte": l["motivo_descarte"].where(l["status_final"] == "DESCARTADO"),
        "ts_entrega": _ts(l["ts_entrega"]), "refeicoes": l["refeicoes"].round(2), "custo_caixa": l["custo_caixa"],
    })
    saida = {
        "regioes": r,
        "doadores": d[["codigo", "documento_hash", "tipo_doador", "segmento", "regiao", "ipvs_grupo", "lat", "lon",
                       "tem_refrigeracao", "pode_entregar", "aceita_coleta", "abertura_h", "fechamento_h"]],
        "ongs": o[["codigo", "documento_hash", "regiao", "ipvs_grupo", "lat", "lon", "status_aprovacao",
                   "capacidade_kg_dia", "tem_refrigeracao", "tem_freezer", "tem_cozinha", "distribui_cestas",
                   "serve_refeicao", "pode_buscar", "aceita_receber_entrega", "abertura_h", "fechamento_h", "turnos",
                   "categorias_aceitas"]],
        "hubs": h[["codigo", "regiao", "ipvs_grupo", "lat", "lon", "tipo", "validado_admin"]],
        "transportadores": t[["codigo", "modalidade", "veiculo", "refrigerado", "capacidade_kg", "regiao", "lat", "lon"]],
        "lotes": lotes,
        "pedidos": p[["codigo", "ong_codigo", "categoria", "kg", "kg_atendido", "ts_abertura", "ts_expira", "status"]],
    }
    if com_eventos:
        e = pd.read_csv(DADOS / "eventos.csv.gz").rename(columns={"evento_id": "codigo", "lote_id": "lote_codigo"})
        e["ts"] = _ts(e["ts"])
        saida["eventos"] = e[["codigo", "lote_codigo", "ts", "tipo", "ator", "detalhe"]]
    return saida


def _valor(v):
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return None
    return v.item() if hasattr(v, "item") else v


def carregar(url: str, com_eventos: bool = False) -> dict[str, int]:
    import psycopg
    from psycopg import sql

    inseridos = {}
    with psycopg.connect(url, autocommit=False) as c:
        c.execute((RAIZ / "db" / "schema.sql").read_text(encoding="utf-8"))
        for nome, df in tabelas(com_eventos).items():
            colunas = list(df.columns)
            temp = sql.Identifier(f"_carga_{nome}")
            c.execute(sql.SQL("CREATE TEMP TABLE {} (LIKE rede.{} INCLUDING DEFAULTS) ON COMMIT DROP").format(
                temp, sql.Identifier(nome)))
            cols = sql.SQL(", ").join(map(sql.Identifier, colunas))
            with c.cursor().copy(sql.SQL("COPY {} ({}) FROM STDIN").format(temp, cols)) as copia:
                for linha in df.itertuples(index=False):
                    copia.write_row([_valor(v) for v in linha])
            cur = c.execute(sql.SQL("INSERT INTO rede.{} ({}) SELECT {} FROM {} ON CONFLICT (codigo) DO NOTHING"
                                    if nome != "regioes" else
                                    "INSERT INTO rede.{} ({}) SELECT {} FROM {} ON CONFLICT (regiao) DO NOTHING"
                                    ).format(sql.Identifier(nome), cols, cols, temp))
            inseridos[nome] = cur.rowcount
            print(f"{nome}: {cur.rowcount} novas linhas (de {len(df)})", flush=True)
        c.commit()
    return inseridos


if __name__ == "__main__":
    url = os.environ.get("REDE_ALIMENTA_DB_ADMIN_URL")
    if not url:
        sys.exit("Defina REDE_ALIMENTA_DB_ADMIN_URL (conexão de dono do banco; nunca a coloque no código).")
    carregar(url, com_eventos="--com-eventos" in sys.argv)

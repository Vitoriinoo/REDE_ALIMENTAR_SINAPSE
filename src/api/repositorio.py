"""Persistência dos lotes cadastrados pela API: Supabase (PostgreSQL) ou memória.

- `RepositorioPostgres`: usado quando `REDE_ALIMENTA_DATABASE_URL` existe. Conecta com o papel
  `rede_api` (db/schema.sql), que só INSERE lotes/eventos/declarações e só ATUALIZA o desfecho de
  lotes de origem 'api' (RLS). Declaração no banco é só de inclusão (gatilho + REVOKE).
- `RepositorioMemoria`: desenvolvimento e testes. A declaração vai para o repositório em arquivo
  só de inclusão (`src/seguranca/declaracao.py`).

Os dois expõem a mesma interface; as rotas não sabem qual está em uso.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from src.seguranca.declaracao import DeclaracaoAssinada, RepositorioDeclaracoes, json_canonico

CAMPOS_LOTE = ("codigo", "origem", "doador_codigo", "tipo_doador", "segmento", "regiao", "ts_cadastro", "categoria",
               "armazenamento", "peso_kg", "validade_efetiva", "horas_restantes", "rota_expressa", "bloqueio",
               "declaracao_codigo", "ranking", "custo_caixa", "acionou_pago")
CAMPOS_DESFECHO = ("prioridade", "prioridade_fonte", "risco_descarte", "ong_codigo", "ts_aceite_ong",
                   "minutos_ate_match", "modo_logistico", "excecao_redundante", "modalidade", "status_final",
                   "motivo_descarte", "ts_entrega", "refeicoes")


class LoteNaoEncontrado(KeyError):
    pass


def _so_campos(campos, permitidos) -> None:
    """Allowlist de colunas. Exceção explícita, e não assert: assert some com `python -O` (Bandit B101)."""
    if not set(campos) <= set(permitidos):
        raise ValueError(f"campos não permitidos: {sorted(set(campos) - set(permitidos))}")


class RepositorioMemoria:
    nome = "memoria"

    def __init__(self, dir_declaracoes: Path):
        self._lotes: dict[str, dict] = {}
        self._eventos: list[dict] = []
        self._declaracoes = RepositorioDeclaracoes(dir_declaracoes)
        self._trava = threading.Lock()

    def inserir_lote(self, lote: dict) -> None:
        _so_campos(lote, CAMPOS_LOTE + CAMPOS_DESFECHO)
        with self._trava:
            if lote["codigo"] in self._lotes:
                raise ValueError("lote já existe")
            self._lotes[lote["codigo"]] = dict(lote)

    def lote(self, codigo: str) -> dict:
        try:
            return dict(self._lotes[codigo])
        except KeyError:
            raise LoteNaoEncontrado(codigo) from None

    def atualizar_desfecho(self, codigo: str, **campos) -> None:
        _so_campos(campos, CAMPOS_DESFECHO)
        with self._trava:
            self._lotes[codigo].update(campos)

    def inserir_evento(self, lote_codigo: str, tipo: str, ator: str, ts: datetime, detalhe: str = "") -> None:
        self._eventos.append({"lote_codigo": lote_codigo, "tipo": tipo, "ator": ator, "ts": ts, "detalhe": detalhe})

    def inserir_declaracao(self, lote_codigo: str, d: DeclaracaoAssinada) -> None:
        self._declaracoes.salvar(d)

    def declaracao(self, declaracao_id: str) -> DeclaracaoAssinada:
        return self._declaracoes.versoes(declaracao_id)[-1]

    def recentes(self, limite: int = 20) -> list[dict]:
        return sorted(self._lotes.values(), key=lambda l: l["ts_cadastro"], reverse=True)[:limite]

    def _filtrar(self, condicao) -> list[dict]:
        return [dict(l) for l in sorted(self._lotes.values(), key=lambda l: l["ts_cadastro"], reverse=True)
                if condicao(l)]

    def do_doador(self, doador_id: str) -> list[dict]:
        return self._filtrar(lambda l: l["doador_codigo"] == doador_id)[:50]

    def ofertas_da_ong(self, ong_id: str) -> list[dict]:
        return self._filtrar(lambda l: l["status_final"] == "PENDENTE" and l.get("ong_codigo") == ong_id
                             and not l.get("ts_aceite_ong"))

    def entregas_da_ong(self, ong_id: str) -> list[dict]:
        return self._filtrar(lambda l: l["status_final"] == "PENDENTE" and l.get("ong_codigo") == ong_id
                             and l.get("ts_aceite_ong"))

    def historico_da_ong(self, ong_id: str) -> list[dict]:
        return self._filtrar(lambda l: l["status_final"] != "PENDENTE" and l.get("ong_codigo") == ong_id
                             and l.get("ts_aceite_ong"))[:50]


class RepositorioPostgres:
    nome = "postgres"

    def __init__(self, url: str):
        self._url = url

    def _conectar(self):
        import psycopg

        return psycopg.connect(self._url, autocommit=True, connect_timeout=5)

    def inserir_lote(self, lote: dict) -> None:
        from psycopg import sql

        _so_campos(lote, CAMPOS_LOTE + CAMPOS_DESFECHO)  # nome de coluna nunca vem de fora (Bandit B608)
        consulta = sql.SQL("INSERT INTO rede.lotes ({}) VALUES ({})").format(
            sql.SQL(", ").join(map(sql.Identifier, lote)), sql.SQL(", ").join(sql.Placeholder() * len(lote)))
        valores = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in lote.values()]
        with self._conectar() as c:
            c.execute(consulta, valores)

    def lote(self, codigo: str) -> dict:
        import psycopg.rows

        with self._conectar() as c:
            c.row_factory = psycopg.rows.dict_row
            linha = c.execute("SELECT * FROM rede.lotes WHERE codigo = %s", (codigo,)).fetchone()
        if linha is None:
            raise LoteNaoEncontrado(codigo)
        return {k: (float(v) if isinstance(v, Decimal) else v) for k, v in linha.items()}

    def atualizar_desfecho(self, codigo: str, **campos) -> None:
        from psycopg import sql

        _so_campos(campos, CAMPOS_DESFECHO)
        consulta = sql.SQL("UPDATE rede.lotes SET {} WHERE codigo = %s").format(
            sql.SQL(", ").join(sql.SQL("{} = %s").format(sql.Identifier(k)) for k in campos))
        with self._conectar() as c:
            c.execute(consulta, [*campos.values(), codigo])

    def inserir_evento(self, lote_codigo: str, tipo: str, ator: str, ts: datetime, detalhe: str = "") -> None:
        with self._conectar() as c:
            c.execute("INSERT INTO rede.eventos (codigo, lote_codigo, ts, tipo, ator, detalhe) "
                      "VALUES (%s, %s, %s, %s, %s, %s)",
                      (f"E-API-{uuid.uuid4().hex[:12]}", lote_codigo, ts, tipo, ator, detalhe[:200]))

    def inserir_declaracao(self, lote_codigo: str, d: DeclaracaoAssinada) -> None:
        c_ = d.conteudo
        with self._conectar() as c:
            c.execute(
                "INSERT INTO rede.declaracoes (declaracao_codigo, versao, lote_codigo, conteudo, sha256, "
                "assinatura_b64, chave_id, sha256_versao_anterior) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
                (c_["declaracao_id"], c_["versao"], lote_codigo, json_canonico(c_).decode(), d.sha256, d.assinatura,
                 d.chave_id, c_.get("hash_versao_anterior")))

    def declaracao(self, declaracao_id: str) -> DeclaracaoAssinada:
        from src.seguranca.declaracao import ALGORITMO

        with self._conectar() as c:
            linha = c.execute("SELECT conteudo, sha256, assinatura_b64, chave_id FROM rede.declaracoes "
                              "WHERE declaracao_codigo = %s ORDER BY versao DESC LIMIT 1", (declaracao_id,)).fetchone()
        if linha is None:
            raise LoteNaoEncontrado(declaracao_id)
        conteudo = linha[0] if isinstance(linha[0], dict) else json.loads(linha[0])
        return DeclaracaoAssinada(conteudo, linha[1], linha[2], ALGORITMO, linha[3])

    def recentes(self, limite: int = 20) -> list[dict]:
        import psycopg.rows

        with self._conectar() as c:
            c.row_factory = psycopg.rows.dict_row
            return c.execute("SELECT codigo, regiao, categoria, peso_kg, prioridade, status_final, ts_cadastro "
                             "FROM rede.lotes WHERE origem = 'api' ORDER BY ts_cadastro DESC LIMIT %s",
                             (limite,)).fetchall()

    def _consulta(self, onde: str, parametros: tuple) -> list[dict]:
        """`onde` é sempre um texto FIXO deste arquivo; valores só como parâmetros."""
        import psycopg.rows
        from psycopg import sql

        consulta = sql.SQL("SELECT * FROM rede.lotes WHERE origem = 'api' AND {} ORDER BY ts_cadastro DESC LIMIT 50"
                           ).format(sql.SQL(onde))
        with self._conectar() as c:
            c.row_factory = psycopg.rows.dict_row
            linhas = c.execute(consulta, parametros).fetchall()
        return [{k: (float(v) if isinstance(v, Decimal) else v) for k, v in l.items()} for l in linhas]

    def do_doador(self, doador_id: str) -> list[dict]:
        return self._consulta("doador_codigo = %s", (doador_id,))

    def ofertas_da_ong(self, ong_id: str) -> list[dict]:
        return self._consulta("status_final = 'PENDENTE' AND ong_codigo = %s AND ts_aceite_ong IS NULL", (ong_id,))

    def entregas_da_ong(self, ong_id: str) -> list[dict]:
        return self._consulta("status_final = 'PENDENTE' AND ong_codigo = %s AND ts_aceite_ong IS NOT NULL",
                              (ong_id,))

    def historico_da_ong(self, ong_id: str) -> list[dict]:
        return self._consulta("status_final <> 'PENDENTE' AND ong_codigo = %s AND ts_aceite_ong IS NOT NULL",
                              (ong_id,))

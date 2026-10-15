"""Esquema relacional (db/schema.sql): NUMERIC em toda quantidade, RLS e tabelas só de inclusão.

Os testes estáticos rodam sempre. Os de integração só rodam com um PostgreSQL de teste em
REDE_ALIMENTA_PG_TESTE (no GitHub Actions, um container postgres:16 descartável).
"""

import os
import re
from pathlib import Path

import pytest

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def _sql_sem_comentarios() -> str:
    return re.sub(r"--[^\n]*", "", SCHEMA.read_text(encoding="utf-8"))


def _tabelas() -> list[str]:
    return re.findall(r"CREATE TABLE IF NOT EXISTS rede\.(\w+)", _sql_sem_comentarios())


# --- Estáticos -------------------------------------------------------------------------------
def test_nenhum_tipo_inteiro_ou_ponto_flutuante():
    """Checklist do professor (item 14): NUMERIC no lugar de INTEGER; dinheiro nunca em float."""
    proibidos = r"\b(INTEGER|INT|INT2|INT4|INT8|BIGINT|SMALLINT|SERIAL|BIGSERIAL|SMALLSERIAL|REAL|FLOAT\d*|DOUBLE PRECISION|MONEY)\b"
    achados = re.findall(proibidos, _sql_sem_comentarios(), flags=re.IGNORECASE)
    assert achados == [], f"tipos proibidos no esquema: {sorted(set(achados))}"


def test_dinheiro_e_numeric_10_2():
    sql = _sql_sem_comentarios()
    for coluna in ("custo_caixa", "valor"):
        assert re.search(rf"\b{coluna}\s+NUMERIC\(10,2\)", sql), coluna


def test_toda_tabela_tem_chave_uuid_e_rls():
    sql = _sql_sem_comentarios()
    tabelas = _tabelas()
    assert len(tabelas) >= 10
    rls = re.search(r"ARRAY\[([^\]]+)\]\s+LOOP\s+EXECUTE format\('ALTER TABLE rede\.%I ENABLE ROW LEVEL SECURITY'", sql)
    com_rls = set(re.findall(r"'(\w+)'", rls.group(1)))
    assert set(tabelas) == com_rls, f"sem RLS: {set(tabelas) - com_rls}"
    for t in tabelas:
        bloco = re.search(rf"CREATE TABLE IF NOT EXISTS rede\.{t} \((.*?)\n\);", sql, flags=re.S).group(1)
        assert re.search(r"\bid\s+UUID PRIMARY KEY", bloco), t


def test_declaracoes_e_registro_sao_so_de_inclusao():
    sql = _sql_sem_comentarios()
    for t in ("declaracoes", "registro_auditavel"):
        assert re.search(rf"BEFORE UPDATE OR DELETE ON rede\.{t}", sql), t
        assert re.search(rf"BEFORE TRUNCATE ON rede\.{t}", sql), t
    assert re.search(r"REVOKE UPDATE, DELETE, TRUNCATE ON rede\.declaracoes, rede\.registro_auditavel FROM rede_api", sql)


def test_dashboard_so_le_visoes():
    sql = _sql_sem_comentarios()
    concessoes = re.findall(r"GRANT SELECT ON ([^;]+) TO rede_dashboard", sql)
    objetos = {o.strip() for c in concessoes for o in c.split(",")}
    assert objetos and all(o.startswith("rede.vw_") for o in objetos), objetos


def test_sem_senha_no_esquema():
    assert not re.search(r"PASSWORD", _sql_sem_comentarios(), flags=re.IGNORECASE)


def test_contas_sem_dado_pessoal_em_claro_e_api_sem_update():
    """Login real: e-mail e documento só como HMAC, senha só como scrypt; a API cria e lê, nunca altera."""
    sql = _sql_sem_comentarios()
    bloco = re.search(r"CREATE TABLE IF NOT EXISTS rede\.contas \((.*?)\n\);", sql, flags=re.S).group(1)
    colunas = set(re.findall(r"^\s+(\w+)\s+(?:TEXT|UUID|TIMESTAMPTZ)", bloco, flags=re.M))
    assert {"email_hash", "documento_hash", "senha_hash"} <= colunas
    assert not colunas & {"email", "documento", "cpf", "cnpj", "senha"}
    assert "GRANT SELECT, INSERT ON rede.contas TO rede_api" in sql
    assert not re.search(r"GRANT[^;]*(UPDATE|DELETE)[^;]*rede\.contas", sql)
    migracao = (SCHEMA.parent / "migracoes" / "2026-10-15_contas.sql").read_text(encoding="utf-8")
    assert bloco in re.sub(r"--[^\n]*", "", migracao)  # migração e esquema não divergem


# --- Integração (PostgreSQL real) --------------------------------------------------------------
PG = os.environ.get("REDE_ALIMENTA_PG_TESTE")
integracao = pytest.mark.skipif(not PG, reason="sem REDE_ALIMENTA_PG_TESTE (roda no CI com postgres:16)")


@pytest.fixture(scope="module")
def conexao():
    psycopg = pytest.importorskip("psycopg")
    with psycopg.connect(PG, autocommit=True) as c:
        c.execute("DROP SCHEMA IF EXISTS rede CASCADE")
        c.execute(SCHEMA.read_text(encoding="utf-8"))
        c.execute(SCHEMA.read_text(encoding="utf-8"))  # idempotente
        c.execute("""
            INSERT INTO rede.regioes (regiao, municipio, setores_classificados, setores_vulneraveis, ipvs_medio,
                                      lat, lon, pct_vulneravel, indice_vulnerabilidade)
            VALUES ('Diadema', 'Diadema', 738, 284, 3.687, -23.69, -46.61, 0.38, 0.90);
            INSERT INTO rede.lotes (codigo, origem, tipo_doador, segmento, regiao, ts_cadastro, categoria,
                                    armazenamento, peso_kg, status_final)
            VALUES ('L-T1', 'simulacao', 'PJ', 'padaria', 'Diadema', now(), 'padaria', 'ambiente', 12.5, 'PENDENTE');
            INSERT INTO rede.declaracoes (declaracao_codigo, versao, lote_codigo, conteudo, sha256, assinatura_b64, chave_id)
            VALUES ('DEC-1', 1, 'L-T1', '{}', repeat('a', 64), 'eA==', 'k1');
        """)
        yield c


@integracao
def test_api_cria_e_le_conta_mas_nao_altera(conexao):
    psycopg = pytest.importorskip("psycopg")
    h = "b" * 64
    conexao.execute("SET ROLE rede_api")
    try:
        conexao.execute("INSERT INTO rede.contas (codigo, email_hash, senha_hash, papel, nome, documento_hash, status) "
                        "VALUES ('O-T1', %s, 'scrypt$x', 'ong', 'ONG Teste', %s, 'ativa')", (h, h))
        assert conexao.execute("SELECT status FROM rede.contas WHERE codigo = 'O-T1'").fetchone()[0] == "ativa"
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conexao.execute("UPDATE rede.contas SET status = 'pendente' WHERE codigo = 'O-T1'")
    finally:
        conexao.execute("RESET ROLE")


@integracao
def test_declaracao_recusa_update_delete_e_truncate_ate_do_dono(conexao):
    import psycopg
    for comando in ("UPDATE rede.declaracoes SET sha256 = repeat('b', 64)",
                    "DELETE FROM rede.declaracoes", "TRUNCATE rede.declaracoes"):
        with pytest.raises(psycopg.errors.RaiseException, match="só de inclusão"):
            conexao.execute(comando)


@integracao
def test_dinheiro_float_vira_numeric_exato(conexao):
    conexao.execute("UPDATE rede.lotes SET custo_caixa = 0.1 + 0.2 WHERE codigo = 'L-T1'")
    valor = conexao.execute("SELECT custo_caixa FROM rede.lotes WHERE codigo = 'L-T1'").fetchone()[0]
    assert str(valor) == "0.30"


@integracao
def test_papel_da_api_nao_altera_historico_simulado_nem_declaracao(conexao):
    import psycopg
    conexao.execute("SET ROLE rede_api")
    try:
        r = conexao.execute("UPDATE rede.lotes SET status_final = 'ENTREGUE' WHERE codigo = 'L-T1'")
        assert r.rowcount == 0  # RLS: só lotes de origem 'api'
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conexao.execute("DELETE FROM rede.declaracoes")
    finally:
        conexao.execute("RESET ROLE")


@integracao
def test_papel_do_dashboard_nao_le_tabelas(conexao):
    import psycopg
    conexao.execute("SET ROLE rede_dashboard")
    try:
        assert conexao.execute("SELECT count(*) FROM rede.vw_impacto_regiao").fetchone()[0] == 1
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            conexao.execute("SELECT * FROM rede.doadores")
    finally:
        conexao.execute("RESET ROLE")


@integracao
def test_carga_do_ano_simulado_respeita_o_esquema(conexao):
    """O dataset inteiro passa por todas as CHECKs (NUMERIC, faixas, coerências) e alimenta as visões."""
    from src.db.carregar import carregar

    inseridos = carregar(PG)
    assert inseridos["lotes"] == 24135 and inseridos["ongs"] == 60
    assert carregar(PG)["lotes"] == 0  # idempotente
    entregues = conexao.execute("SELECT sum(entregues) FROM rede.vw_impacto_regiao").fetchone()[0]
    assert entregues == conexao.execute(
        "SELECT count(*) FROM rede.lotes WHERE status_final = 'ENTREGUE' AND ong_codigo IS NOT NULL").fetchone()[0]


@integracao
def test_trilha_de_auditoria_no_banco_sobrevive_ao_reinicio_e_e_so_inclusao(conexao, tmp_path):
    """JSONB ida e volta não quebra o HMAC; a cadeia continua do banco; UPDATE é recusado até para o dono."""
    import psycopg

    from src.observabilidade.registro import AuditoriaPostgres, RegistroAuditavel, Trilha

    def registro(pasta):
        return RegistroAuditavel(pasta, chave=b"k", auditoria_db=AuditoriaPostgres(PG))

    registro(tmp_path / "a").registrar(Trilha.AUDITORIA, componente="api.lotes", acao="CADASTRO_LOTE",
                                       ator="doador:abc", papel="doador", detalhes={"peso_kg": 12.5, "ok": True})
    depois = registro(tmp_path / "b")  # disco novo, como num deploy do Render
    depois.registrar(Trilha.AUDITORIA, componente="api.lotes", acao="ACEITE_ONG", ator="ong:xyz", papel="ong")
    assert depois.verificar_cadeia() == [] and len(depois.ler(Trilha.AUDITORIA)) == 2
    with pytest.raises(psycopg.errors.RaiseException, match="só de inclusão"):
        conexao.execute("UPDATE rede.registro_auditavel SET acao = 'X'")

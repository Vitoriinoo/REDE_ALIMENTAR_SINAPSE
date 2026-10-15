-- =============================================================================================
-- Rede Alimenta IA: esquema relacional (Supabase / PostgreSQL 15+)
-- =============================================================================================
-- Regras do esquema (checklist do professor, item 14; SDD §5):
--   * Toda quantidade, contagem, medida ou valor é NUMERIC. Nenhum INTEGER/FLOAT
--     (tests/test_schema.py barra o pipeline se aparecer). Dinheiro = NUMERIC(10,2).
--   * Chave primária técnica = UUID. O código legível (L-000001, D-0001, ...) é TEXT UNIQUE e é
--     ele que as chaves estrangeiras usam, para o dataset simulado entrar sem tradução.
--   * Menor privilégio: a API (rede_api) e o dashboard (rede_dashboard) têm papéis próprios. O
--     dashboard só LÊ visões agregadas, nunca as tabelas.
--   * Declarações e registro auditável são SÓ DE INCLUSÃO: sem UPDATE/DELETE por permissão (REVOKE)
--     e por gatilho (que vale até para o dono das tabelas).
--   * Nenhum dado pessoal em claro: documento só como HMAC-SHA256 (regras 11).
-- Idempotente: pode ser rodado de novo no SQL Editor do Supabase.
-- =============================================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()

-- --- Papéis (sem senha aqui: a senha é definida fora do repositório, ver README §Supabase) --------
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rede_api') THEN CREATE ROLE rede_api NOLOGIN; END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'rede_dashboard') THEN CREATE ROLE rede_dashboard NOLOGIN; END IF;
END $$;

CREATE SCHEMA IF NOT EXISTS rede;
REVOKE ALL ON SCHEMA rede FROM PUBLIC;
GRANT USAGE ON SCHEMA rede TO rede_api, rede_dashboard;

-- --- Referência ---------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rede.regioes (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    regiao                 TEXT NOT NULL UNIQUE,
    municipio              TEXT NOT NULL,
    setores_classificados  NUMERIC(8,0) NOT NULL CHECK (setores_classificados >= 0),
    setores_vulneraveis    NUMERIC(8,0) NOT NULL CHECK (setores_vulneraveis >= 0),
    ipvs_medio             NUMERIC(6,4) NOT NULL,
    lat                    NUMERIC(9,6) NOT NULL,
    lon                    NUMERIC(9,6) NOT NULL,
    pct_vulneravel         NUMERIC(6,4) NOT NULL CHECK (pct_vulneravel BETWEEN 0 AND 1),
    indice_vulnerabilidade NUMERIC(6,4) NOT NULL CHECK (indice_vulnerabilidade BETWEEN 0 AND 1)
);

-- --- Entidades ----------------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rede.doadores (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo           TEXT NOT NULL UNIQUE,
    documento_hash   TEXT NOT NULL CHECK (documento_hash ~ '^[0-9a-f]{64}$'),  -- HMAC-SHA256, nunca o CPF/CNPJ
    tipo_doador      TEXT NOT NULL CHECK (tipo_doador IN ('PF', 'PJ')),
    segmento         TEXT NOT NULL,
    regiao           TEXT NOT NULL REFERENCES rede.regioes (regiao),
    ipvs_grupo       NUMERIC(1,0) NOT NULL CHECK (ipvs_grupo BETWEEN 1 AND 6),
    lat              NUMERIC(9,6) NOT NULL,  -- PF: centroide do setor (regras 11)
    lon              NUMERIC(9,6) NOT NULL,
    tem_refrigeracao BOOLEAN NOT NULL,
    pode_entregar    BOOLEAN NOT NULL,              -- capacidade
    aceita_coleta    BOOLEAN NOT NULL DEFAULT TRUE, -- restrição (v2.1): falso = "só entrega"
    abertura_h       NUMERIC(4,2) NOT NULL CHECK (abertura_h BETWEEN 0 AND 24),
    fechamento_h     NUMERIC(4,2) NOT NULL CHECK (fechamento_h BETWEEN 0 AND 24),
    criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (aceita_coleta OR pode_entregar),  -- quem não aceita coleta precisa entregar
    CHECK (abertura_h < fechamento_h)
);

CREATE TABLE IF NOT EXISTS rede.ongs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo                 TEXT NOT NULL UNIQUE,
    documento_hash         TEXT NOT NULL CHECK (documento_hash ~ '^[0-9a-f]{64}$'),
    regiao                 TEXT NOT NULL REFERENCES rede.regioes (regiao),
    ipvs_grupo             NUMERIC(1,0) NOT NULL CHECK (ipvs_grupo BETWEEN 1 AND 6),
    lat                    NUMERIC(9,6) NOT NULL,
    lon                    NUMERIC(9,6) NOT NULL,
    status_aprovacao       TEXT NOT NULL CHECK (status_aprovacao IN ('pendente', 'aprovada', 'reprovada')),
    capacidade_kg_dia      NUMERIC(10,3) NOT NULL CHECK (capacidade_kg_dia > 0),
    tem_refrigeracao       BOOLEAN NOT NULL,
    tem_freezer            BOOLEAN NOT NULL,
    tem_cozinha            BOOLEAN NOT NULL,
    distribui_cestas       BOOLEAN NOT NULL,
    serve_refeicao         BOOLEAN NOT NULL,
    pode_buscar            BOOLEAN NOT NULL,              -- capacidade
    aceita_receber_entrega BOOLEAN NOT NULL DEFAULT TRUE, -- restrição (v2.1): falso = "só busca"
    abertura_h             NUMERIC(4,2) NOT NULL CHECK (abertura_h BETWEEN 0 AND 24),
    fechamento_h           NUMERIC(4,2) NOT NULL CHECK (fechamento_h BETWEEN 0 AND 24),
    turnos                 TEXT NOT NULL,
    categorias_aceitas     TEXT NOT NULL,
    criado_em              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (aceita_receber_entrega OR pode_buscar),
    CHECK (NOT tem_freezer OR tem_refrigeracao)
);

CREATE TABLE IF NOT EXISTS rede.hubs (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo         TEXT NOT NULL UNIQUE,
    regiao         TEXT NOT NULL REFERENCES rede.regioes (regiao),
    ipvs_grupo     NUMERIC(1,0) NOT NULL CHECK (ipvs_grupo BETWEEN 1 AND 6),
    lat            NUMERIC(9,6) NOT NULL,
    lon            NUMERIC(9,6) NOT NULL,
    tipo           TEXT NOT NULL,
    validado_admin BOOLEAN NOT NULL
);

CREATE TABLE IF NOT EXISTS rede.transportadores (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo        TEXT NOT NULL UNIQUE,
    modalidade    TEXT NOT NULL,
    veiculo       TEXT NOT NULL,
    refrigerado   BOOLEAN NOT NULL,
    capacidade_kg NUMERIC(10,3) NOT NULL CHECK (capacidade_kg > 0),
    regiao        TEXT NOT NULL REFERENCES rede.regioes (regiao),
    lat           NUMERIC(9,6) NOT NULL,
    lon           NUMERIC(9,6) NOT NULL
);

-- --- Contas do login (e-mail e senha). Nada pessoal em claro: e-mail e CPF/CNPJ só como HMAC-SHA256,
--     senha só como scrypt. `codigo` liga a conta ao registro operacional (D-0008, O-005, V-001, A-01). -----
CREATE TABLE IF NOT EXISTS rede.contas (
    id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo         TEXT NOT NULL UNIQUE,
    email_hash     TEXT NOT NULL UNIQUE CHECK (email_hash ~ '^[0-9a-f]{64}$'),
    senha_hash     TEXT NOT NULL CHECK (senha_hash LIKE 'scrypt$%'),
    papel          TEXT NOT NULL CHECK (papel IN ('doador', 'ong', 'transportador', 'admin')),
    nome           TEXT NOT NULL CHECK (length(nome) BETWEEN 2 AND 120),
    documento_hash TEXT NOT NULL CHECK (documento_hash ~ '^[0-9a-f]{64}$'),
    tipo_doador    TEXT CHECK (tipo_doador IN ('PF', 'PJ')),
    veiculo        TEXT CHECK (veiculo IN ('moto', 'carro', 'utilitario')),
    status         TEXT NOT NULL CHECK (status IN ('ativa', 'pendente')),
    criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (papel, documento_hash),
    CHECK ((papel = 'doador') = (tipo_doador IS NOT NULL)),
    CHECK ((papel = 'transportador') = (veiculo IS NOT NULL))
);

-- --- Lotes: cadastro + desfecho -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rede.lotes (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo              TEXT NOT NULL UNIQUE,
    origem              TEXT NOT NULL CHECK (origem IN ('simulacao', 'api')),
    doador_codigo       TEXT REFERENCES rede.doadores (codigo),
    tipo_doador         TEXT NOT NULL CHECK (tipo_doador IN ('PF', 'PJ')),
    segmento            TEXT NOT NULL,
    regiao              TEXT NOT NULL REFERENCES rede.regioes (regiao),
    ts_cadastro         TIMESTAMPTZ NOT NULL,
    categoria           TEXT NOT NULL,
    armazenamento       TEXT NOT NULL,
    peso_kg             NUMERIC(10,3) NOT NULL CHECK (peso_kg > 0),
    validade_efetiva    TIMESTAMPTZ,
    horas_restantes     NUMERIC(10,2),
    rota_expressa       BOOLEAN NOT NULL DEFAULT FALSE,
    bloqueio            TEXT,  -- motivo do bloqueio no cadastro (validade, questionário), se houver
    prioridade          TEXT CHECK (prioridade IN ('CRITICA', 'ALTA', 'MEDIA', 'BAIXA')),
    prioridade_fonte    TEXT,  -- 'modelo', 'regra', 'piso_seguranca' (regras 10.3)
    risco_descarte      NUMERIC(5,4) CHECK (risco_descarte BETWEEN 0 AND 1),
    ong_codigo          TEXT REFERENCES rede.ongs (codigo),
    ts_aceite_ong       TIMESTAMPTZ,
    minutos_ate_match   NUMERIC(10,1) CHECK (minutos_ate_match >= 0),
    modo_logistico      TEXT CHECK (modo_logistico IN ('direto', 'via_hub')),
    excecao_redundante  BOOLEAN NOT NULL DEFAULT FALSE,
    modalidade          TEXT,
    acionou_pago        BOOLEAN NOT NULL DEFAULT FALSE,
    status_final        TEXT NOT NULL CHECK (status_final IN ('PENDENTE', 'BLOQUEADO', 'ENTREGUE', 'DESCARTADO')),
    motivo_descarte     TEXT,
    ts_entrega          TIMESTAMPTZ,
    refeicoes           NUMERIC(12,2) CHECK (refeicoes >= 0),
    custo_caixa         NUMERIC(10,2) CHECK (custo_caixa >= 0),  -- dinheiro: NUMERIC(10,2), nunca float
    declaracao_codigo   TEXT,   -- Declaração de Doação do lote (rede.declaracoes)
    ranking             JSONB,  -- ONGs ofertadas, na ordem, com score (auditoria do matching)
    criado_em           TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS lotes_regiao_status ON rede.lotes (regiao, status_final);
CREATE INDEX IF NOT EXISTS lotes_ts ON rede.lotes (ts_cadastro);

CREATE TABLE IF NOT EXISTS rede.pedidos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo      TEXT NOT NULL UNIQUE,
    ong_codigo  TEXT NOT NULL REFERENCES rede.ongs (codigo),
    categoria   TEXT NOT NULL,
    kg          NUMERIC(10,3) NOT NULL CHECK (kg > 0),
    kg_atendido NUMERIC(10,3) NOT NULL DEFAULT 0 CHECK (kg_atendido >= 0),
    ts_abertura TIMESTAMPTZ NOT NULL,
    ts_expira   TIMESTAMPTZ NOT NULL CHECK (ts_expira <= ts_abertura + INTERVAL '7 days'),
    status      TEXT NOT NULL
);

-- Trilha do processo de cada lote (o "o que aconteceu"; a trilha de auditoria fica em registro_auditavel).
CREATE TABLE IF NOT EXISTS rede.eventos (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    codigo     TEXT NOT NULL UNIQUE,
    lote_codigo TEXT NOT NULL REFERENCES rede.lotes (codigo),
    ts         TIMESTAMPTZ NOT NULL,
    tipo       TEXT NOT NULL,
    ator       TEXT NOT NULL,  -- pseudônimo (papel:id), nunca nome
    detalhe    TEXT
);
CREATE INDEX IF NOT EXISTS eventos_lote ON rede.eventos (lote_codigo);

-- --- Caixa solidário: livro-caixa (a plataforma não guarda dinheiro, regras 9) -------------------
CREATE TABLE IF NOT EXISTS rede.caixa_lancamentos (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lote_codigo TEXT REFERENCES rede.lotes (codigo),
    ong_codigo  TEXT NOT NULL REFERENCES rede.ongs (codigo),
    tipo        TEXT NOT NULL CHECK (tipo IN ('aporte', 'entrega_paga', 'estorno')),
    valor       NUMERIC(10,2) NOT NULL CHECK (valor > 0),
    aprovacao   TEXT NOT NULL CHECK (aprovacao IN ('confirmacao_ong', 'gestor_caixa')),
    aprovado_por TEXT NOT NULL,  -- pseudônimo; quem pede não aprova (segregação de funções)
    comprovante_sha256 TEXT CHECK (comprovante_sha256 ~ '^[0-9a-f]{64}$'),
    ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- --- Declarações de doação: SÓ INCLUSÃO, versionadas e encadeadas por hash (regras 4.5) ----------
CREATE TABLE IF NOT EXISTS rede.declaracoes (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    declaracao_codigo    TEXT NOT NULL,
    versao               NUMERIC(4,0) NOT NULL CHECK (versao >= 1),
    lote_codigo          TEXT NOT NULL REFERENCES rede.lotes (codigo),
    conteudo             JSONB NOT NULL,  -- JSON canônico (doador pseudonimizado)
    sha256               TEXT NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    assinatura_b64       TEXT NOT NULL,   -- RSA-PSS 3072 sobre o JSON canônico
    chave_id             TEXT NOT NULL,   -- impressão digital da chave pública que verifica
    sha256_versao_anterior TEXT CHECK (sha256_versao_anterior ~ '^[0-9a-f]{64}$'),
    emitida_em           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (declaracao_codigo, versao),
    CHECK ((versao = 1) = (sha256_versao_anterior IS NULL))
);

-- --- Registro auditável: SÓ INCLUSÃO, cadeia HMAC (regras 10.1) -----------------------------------
CREATE TABLE IF NOT EXISTS rede.registro_auditavel (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sequencia    NUMERIC(20,0) NOT NULL UNIQUE,
    trilha       TEXT NOT NULL CHECK (trilha IN ('operacional', 'auditoria')),
    ts           TIMESTAMPTZ NOT NULL,
    acao         TEXT NOT NULL,
    ator         TEXT NOT NULL,  -- pseudônimo HMAC
    registro     JSONB NOT NULL, -- já minimizado (sem dado pessoal em claro)
    hash_anterior TEXT NOT NULL,
    hash         TEXT NOT NULL UNIQUE
);

CREATE OR REPLACE FUNCTION rede.recusar_alteracao() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'tabela % é só de inclusão: % recusado', TG_TABLE_NAME, TG_OP;
END $$;

DROP TRIGGER IF EXISTS declaracoes_so_inclusao ON rede.declaracoes;
CREATE TRIGGER declaracoes_so_inclusao BEFORE UPDATE OR DELETE ON rede.declaracoes
    FOR EACH ROW EXECUTE FUNCTION rede.recusar_alteracao();
DROP TRIGGER IF EXISTS declaracoes_sem_truncate ON rede.declaracoes;
CREATE TRIGGER declaracoes_sem_truncate BEFORE TRUNCATE ON rede.declaracoes
    FOR EACH STATEMENT EXECUTE FUNCTION rede.recusar_alteracao();
DROP TRIGGER IF EXISTS registro_so_inclusao ON rede.registro_auditavel;
CREATE TRIGGER registro_so_inclusao BEFORE UPDATE OR DELETE ON rede.registro_auditavel
    FOR EACH ROW EXECUTE FUNCTION rede.recusar_alteracao();
DROP TRIGGER IF EXISTS registro_sem_truncate ON rede.registro_auditavel;
CREATE TRIGGER registro_sem_truncate BEFORE TRUNCATE ON rede.registro_auditavel
    FOR EACH STATEMENT EXECUTE FUNCTION rede.recusar_alteracao();

-- --- Visões do dashboard: só agregados, sem identificador de pessoa ------------------------------
-- Impacto por região: kg/refeições pela região da ONG que RECEBEU (destino); lotes e descartes pela
-- região do doador (origem, onde o alimento foi perdido).
DROP VIEW IF EXISTS rede.vw_impacto_regiao;
CREATE VIEW rede.vw_impacto_regiao AS
WITH destino AS (
    SELECT o.regiao, count(*) AS entregues, sum(l.peso_kg) AS kg_salvos, sum(l.refeicoes) AS refeicoes
    FROM rede.lotes l JOIN rede.ongs o ON o.codigo = l.ong_codigo
    WHERE l.status_final = 'ENTREGUE' GROUP BY o.regiao
), origem AS (
    SELECT regiao, count(*) AS lotes, count(*) FILTER (WHERE status_final = 'DESCARTADO') AS descartados
    FROM rede.lotes GROUP BY regiao
)
SELECT r.regiao, r.municipio, r.lat, r.lon, r.indice_vulnerabilidade,
       coalesce(og.lotes, 0) AS lotes, coalesce(d.entregues, 0) AS entregues,
       coalesce(og.descartados, 0) AS descartados, coalesce(d.kg_salvos, 0) AS kg_salvos,
       coalesce(d.refeicoes, 0) AS refeicoes
FROM rede.regioes r LEFT JOIN destino d ON d.regiao = r.regiao LEFT JOIN origem og ON og.regiao = r.regiao;

DROP VIEW IF EXISTS rede.vw_impacto_mensal;
CREATE VIEW rede.vw_impacto_mensal AS
SELECT date_trunc('month', ts_cadastro AT TIME ZONE 'America/Sao_Paulo') AS mes, origem,
       count(*) FILTER (WHERE status_final IN ('ENTREGUE', 'DESCARTADO'))  AS lotes_aceitos,
       count(*) FILTER (WHERE status_final = 'DESCARTADO')                 AS descartados,
       coalesce(sum(peso_kg)  FILTER (WHERE status_final = 'ENTREGUE'), 0) AS kg_salvos,
       coalesce(sum(refeicoes) FILTER (WHERE status_final = 'ENTREGUE'), 0) AS refeicoes,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY minutos_ate_match)      AS mediana_match_min,
       avg(minutos_ate_match)                                              AS media_match_min
FROM rede.lotes GROUP BY 1, 2;

DROP VIEW IF EXISTS rede.vw_match_prioridade;
CREATE VIEW rede.vw_match_prioridade AS
SELECT prioridade, count(minutos_ate_match) AS matches,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY minutos_ate_match) AS mediana_min,
       avg(minutos_ate_match) AS media_min
FROM rede.lotes WHERE minutos_ate_match IS NOT NULL GROUP BY prioridade;

-- KPI do painel: mediana de TODOS os matches (a mediana das medianas por prioridade daria outro número).
DROP VIEW IF EXISTS rede.vw_match_geral;
CREATE VIEW rede.vw_match_geral AS
SELECT count(minutos_ate_match) AS matches,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY minutos_ate_match) AS mediana_min,
       avg(minutos_ate_match) AS media_min
FROM rede.lotes WHERE minutos_ate_match IS NOT NULL;

-- Mapa de calor: refeições pelo local da ONG que RECEBEU (onde a comida chegou), em grade de ~1 km.
DROP VIEW IF EXISTS rede.vw_calor_entregas;
CREATE VIEW rede.vw_calor_entregas AS
SELECT round(o.lat, 2) AS lat, round(o.lon, 2) AS lon,
       sum(l.peso_kg) AS kg_salvos, sum(l.refeicoes) AS refeicoes
FROM rede.lotes l JOIN rede.ongs o ON o.codigo = l.ong_codigo
WHERE l.status_final = 'ENTREGUE'
GROUP BY 1, 2;

DROP VIEW IF EXISTS rede.vw_lotes_recentes;
CREATE VIEW rede.vw_lotes_recentes AS
SELECT codigo, origem, regiao, categoria, peso_kg, prioridade, prioridade_fonte, risco_descarte,
       status_final, ts_cadastro
FROM rede.lotes WHERE origem = 'api' ORDER BY ts_cadastro DESC LIMIT 50;

-- --- Permissões: menor privilégio ---------------------------------------------------------------
REVOKE ALL ON ALL TABLES IN SCHEMA rede FROM PUBLIC, rede_api, rede_dashboard;
-- API: lê o cadastro, insere lotes/eventos/declarações/registro; atualiza só o desfecho do lote.
GRANT SELECT ON rede.regioes, rede.doadores, rede.ongs, rede.hubs, rede.transportadores, rede.pedidos TO rede_api;
GRANT SELECT, INSERT ON rede.lotes, rede.eventos, rede.declaracoes, rede.registro_auditavel, rede.caixa_lancamentos TO rede_api;
GRANT UPDATE (prioridade, prioridade_fonte, risco_descarte, ong_codigo, ts_aceite_ong, minutos_ate_match,
              modo_logistico, excecao_redundante, modalidade, acionou_pago, status_final, motivo_descarte,
              ts_entrega, refeicoes, custo_caixa) ON rede.lotes TO rede_api;
-- Contas: a API cria e lê; aprovar conta pendente ou trocar senha é ação do dono do banco (fora da API).
GRANT SELECT, INSERT ON rede.contas TO rede_api;
-- Nunca UPDATE/DELETE em declaração e registro (além do gatilho, que vale até para o dono).
REVOKE UPDATE, DELETE, TRUNCATE ON rede.declaracoes, rede.registro_auditavel FROM rede_api;
-- Dashboard: só as visões agregadas.
GRANT SELECT ON rede.vw_impacto_regiao, rede.vw_impacto_mensal, rede.vw_match_prioridade, rede.vw_match_geral,
                rede.vw_calor_entregas, rede.vw_lotes_recentes TO rede_dashboard;

-- --- RLS: bloqueio por padrão; cada papel só enxerga o que a política libera ---------------------
DO $$ DECLARE t TEXT; BEGIN
    FOREACH t IN ARRAY ARRAY['regioes','doadores','ongs','hubs','transportadores','contas','lotes','pedidos',
                             'eventos','caixa_lancamentos','declaracoes','registro_auditavel'] LOOP
        EXECUTE format('ALTER TABLE rede.%I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS api_le ON rede.%I', t);
        EXECUTE format('CREATE POLICY api_le ON rede.%I FOR SELECT TO rede_api USING (true)', t);
    END LOOP;
    FOREACH t IN ARRAY ARRAY['contas','lotes','eventos','declaracoes','registro_auditavel','caixa_lancamentos'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS api_inclui ON rede.%I', t);
        EXECUTE format('CREATE POLICY api_inclui ON rede.%I FOR INSERT TO rede_api WITH CHECK (true)', t);
    END LOOP;
END $$;
-- A API só cria/atualiza lotes de origem 'api': o histórico simulado é imutável para ela.
DROP POLICY IF EXISTS api_inclui ON rede.lotes;
CREATE POLICY api_inclui ON rede.lotes FOR INSERT TO rede_api WITH CHECK (origem = 'api');
DROP POLICY IF EXISTS api_atualiza ON rede.lotes;
CREATE POLICY api_atualiza ON rede.lotes FOR UPDATE TO rede_api USING (origem = 'api') WITH CHECK (origem = 'api');
-- As visões rodam com os direitos do dono (padrão do PostgreSQL), então o dashboard lê agregados
-- sem ter SELECT nas tabelas. O schema "rede" não é exposto na API REST do Supabase (PostgREST).

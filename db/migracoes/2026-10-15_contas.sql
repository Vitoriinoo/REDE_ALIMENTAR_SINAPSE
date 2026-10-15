-- Migração 2026-10-15: login real (PLANO-TELAS, decisão 2). Idempotente; o mesmo trecho está em db/schema.sql.
-- Aplicar com a URI de DONO do banco (o papel rede_api não cria tabela, de propósito).

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

REVOKE ALL ON rede.contas FROM PUBLIC, rede_api, rede_dashboard;
GRANT SELECT, INSERT ON rede.contas TO rede_api;
ALTER TABLE rede.contas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS api_le ON rede.contas;
CREATE POLICY api_le ON rede.contas FOR SELECT TO rede_api USING (true);
DROP POLICY IF EXISTS api_inclui ON rede.contas;
CREATE POLICY api_inclui ON rede.contas FOR INSERT TO rede_api WITH CHECK (true);

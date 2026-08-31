CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE SCHEMA IF NOT EXISTS "db-toolchain";

CREATE TABLE IF NOT EXISTS "db-toolchain".anonymize_columns (
    table_schema TEXT NOT NULL DEFAULT 'public',
    table_name TEXT NOT NULL,
    column_name TEXT NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    PRIMARY KEY (table_schema, table_name, column_name)
);

CREATE OR REPLACE FUNCTION "db-toolchain".anonymize_text(plain TEXT, salt TEXT DEFAULT 'db-toolchain')
RETURNS TEXT
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT encode(digest(coalesce(plain, '') || salt, 'sha256'), 'hex');
$$;

CREATE OR REPLACE FUNCTION "db-toolchain".anonymize_integer(val INTEGER, salt TEXT DEFAULT 'db-toolchain')
RETURNS INTEGER
LANGUAGE sql
IMMUTABLE
AS $$
    SELECT abs(hashtext(val::text || salt));
$$;

INSERT INTO "db-toolchain".anonymize_columns (table_name, column_name) VALUES
    ('users', 'name'),
    ('users', 'email'),
    ('orders', 'amount_cents')
ON CONFLICT DO NOTHING;

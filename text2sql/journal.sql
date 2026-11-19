-- À appliquer au PostgreSQL de journalisation existant, jamais aux sources.
-- Le DSN du journal utilise un compte écrivain dédié, distinct de agent_ro.
CREATE SCHEMA IF NOT EXISTS text2sql_journal;
CREATE TABLE IF NOT EXISTS text2sql_journal.events (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    question TEXT NOT NULL,
    source TEXT NOT NULL,
    sql TEXT NOT NULL,
    stage TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS text2sql_journal.experiments (
    id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    git_commit TEXT NOT NULL,
    git_dirty BOOLEAN NOT NULL,
    config JSONB NOT NULL,
    results JSONB NOT NULL
);

-- never-again team tier schema (Postgres 16 + pgvector).
-- Run once against an empty database:  psql "$DATABASE_URL" -f 001_initial.sql

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS failures (
    id          TEXT PRIMARY KEY,
    fingerprint TEXT NOT NULL,
    error       TEXT NOT NULL,
    context     TEXT NOT NULL DEFAULT '',
    solution    TEXT NOT NULL DEFAULT '',
    rule        TEXT,
    scope       TEXT NOT NULL DEFAULT 'local',
    team        TEXT NOT NULL DEFAULT 'local',
    verified    INTEGER NOT NULL DEFAULT 0,
    -- Dimension is intentionally unconstrained because supported embedders may
    -- differ (fastembed's default local model is 384d; Ollama's nomic model is
    -- 768d). Add a dimension-specific ANN index only after choosing one model.
    embedding   vector,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    search      tsvector GENERATED ALWAYS AS (
                    to_tsvector('english', error || ' ' || context || ' ' || solution)
                ) STORED,
    UNIQUE (fingerprint, team, solution)
);

CREATE INDEX IF NOT EXISTS failures_search_idx
    ON failures USING GIN (search);

CREATE INDEX IF NOT EXISTS failures_team_scope_idx
    ON failures (team, scope);

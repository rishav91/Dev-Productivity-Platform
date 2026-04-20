-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Stores every analysis run for querying, debugging, and audit
CREATE TABLE IF NOT EXISTS analysis_runs (
    run_id          TEXT PRIMARY KEY,
    pr_id           TEXT NOT NULL,
    ticket_id       TEXT NOT NULL,
    slack_thread_id TEXT,
    status          TEXT NOT NULL CHECK (status IN ('pending', 'running', 'complete', 'failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    cost_usd        NUMERIC(10, 6),
    latency_ms      INTEGER,
    insight         JSONB,
    langsmith_trace_url TEXT
);

CREATE INDEX IF NOT EXISTS idx_analysis_runs_pr_id     ON analysis_runs (pr_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_ticket_id ON analysis_runs (ticket_id);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_status    ON analysis_runs (status);
CREATE INDEX IF NOT EXISTS idx_analysis_runs_created   ON analysis_runs (created_at DESC);

-- Stores high-confidence insight embeddings for similarity search
-- Only indexed when status='insight' AND confidence >= 0.7
CREATE TABLE IF NOT EXISTS insight_embeddings (
    id              TEXT PRIMARY KEY,           -- same as run_id
    embedding       vector(1536),               -- text-embedding-3-small dimension
    component       TEXT NOT NULL,
    blocker_type    TEXT NOT NULL,
    severity        INTEGER,
    owner           TEXT,
    summary         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_insight_embeddings_component    ON insight_embeddings (component);
CREATE INDEX IF NOT EXISTS idx_insight_embeddings_blocker_type ON insight_embeddings (blocker_type);
CREATE INDEX IF NOT EXISTS idx_insight_embeddings_created      ON insight_embeddings (created_at DESC);
-- IVFFlat index for approximate nearest-neighbor search (build after seeding data)
-- CREATE INDEX ON insight_embeddings USING ivfflat (embedding vector_cosine_ops) WITH (lists = 20);

-- Stores historical PR records for baseline cycle time computation
CREATE TABLE IF NOT EXISTS pr_history (
    pr_id           TEXT PRIMARY KEY,
    author          TEXT NOT NULL,
    title           TEXT NOT NULL,
    changed_files   TEXT[] NOT NULL,
    days_open       INTEGER NOT NULL,
    diff_line_count INTEGER NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    embedding       vector(1536),
    raw             JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pr_history_author  ON pr_history (author);
CREATE INDEX IF NOT EXISTS idx_pr_history_created ON pr_history (created_at DESC);

-- Stores historical InsightPayload records for recurrence detection retrieval
CREATE TABLE IF NOT EXISTS insight_history (
    insight_id      TEXT PRIMARY KEY,
    component       TEXT NOT NULL,
    blocker_type    TEXT,          -- NULL for status='no_issue' or 'insufficient_evidence'
    severity        INTEGER,
    summary         TEXT NOT NULL,
    confidence      NUMERIC(4, 3) NOT NULL,
    status          TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL,
    embedding       vector(1536),
    raw             JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_insight_history_component    ON insight_history (component);
CREATE INDEX IF NOT EXISTS idx_insight_history_blocker_type ON insight_history (blocker_type);
CREATE INDEX IF NOT EXISTS idx_insight_history_created      ON insight_history (created_at DESC);

-- Stage 0: extensions and run bookkeeping only.
-- Decision tables come in stage 2, after the probe has shown the real API shape.

CREATE EXTENSION IF NOT EXISTS vector;

-- One row per CLI command that does work, so every stage reports its own throughput.
CREATE TABLE runs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    command     text NOT NULL,
    args        jsonb NOT NULL DEFAULT '{}'::jsonb,
    started_at  timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    items       integer,
    errors      integer,
    notes       text
);

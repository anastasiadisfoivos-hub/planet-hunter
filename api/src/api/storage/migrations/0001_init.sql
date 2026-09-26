-- Same tables, keys and indexes as the SQLite schema (api/storage/sqlite.py), so the
-- "insert or ignore" idempotency holds via ON CONFLICT DO NOTHING on the same unique keys.
-- player_id is a plain text column: the seam for real accounts later.

CREATE TABLE IF NOT EXISTS traps (
    id TEXT PRIMARY KEY,
    player_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('sky', 'star')),
    ra_deg DOUBLE PRECISION,
    dec_deg DOUBLE PRECISION,
    radius_deg DOUBLE PRECISION,
    tic_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL,
    last_checked_at TIMESTAMPTZ,
    last_tess_marker TEXT
);
CREATE INDEX IF NOT EXISTS traps_player ON traps (player_id, created_at);

CREATE TABLE IF NOT EXISTS discoveries (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    type TEXT NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL,
    record JSONB NOT NULL
);
-- discoveries_with_prefix() does `id LIKE 'prefix%'`; text_pattern_ops makes that an index scan
-- whatever the database collation is.
CREATE INDEX IF NOT EXISTS discoveries_id_prefix ON discoveries (id text_pattern_ops);

CREATE TABLE IF NOT EXISTS catches (
    player_id TEXT NOT NULL,
    discovery_id TEXT NOT NULL REFERENCES discoveries (id),
    trap_id TEXT,
    caught_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (player_id, discovery_id)
);
CREATE INDEX IF NOT EXISTS catches_newest
    ON catches (player_id, caught_at DESC, discovery_id DESC);

CREATE TABLE IF NOT EXISTS jobs (
    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    player_id TEXT NOT NULL,
    trap_id TEXT,
    tic_id BIGINT NOT NULL,
    status TEXT NOT NULL,
    steps JSONB NOT NULL DEFAULT '[]',
    result_ids JSONB NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs (status, seq);

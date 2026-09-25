-- "Analyze a star" (deploy/HOSTING.md R1): one stored result per star, re-computed only when
-- its TESS data marker changes. The result is compact (folded curves binned to <= 1000 points).

CREATE TABLE star_analyses (
    tic_id BIGINT PRIMARY KEY,
    data_marker TEXT,                     -- latest_data_marker() when it was computed
    analyzed_at TIMESTAMPTZ NOT NULL,
    marker_checked_at TIMESTAMPTZ NOT NULL,  -- last time MAST confirmed the marker
    result JSONB NOT NULL
);

-- Names people typed, resolved once ("wasp18" -> 100100827).
CREATE TABLE star_names (
    name_key TEXT PRIMARY KEY,
    tic_id BIGINT NOT NULL,
    resolved_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE analyze_jobs (
    seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    id TEXT NOT NULL UNIQUE,
    tic_id BIGINT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    data_marker TEXT,
    steps JSONB NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);
CREATE INDEX analyze_jobs_status ON analyze_jobs (status, seq);
CREATE INDEX analyze_jobs_tic ON analyze_jobs (tic_id, status);

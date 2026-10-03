-- SQLite twin of ../0003_analyze.sql.

CREATE TABLE star_analyses (
    tic_id INTEGER PRIMARY KEY,
    data_marker TEXT,
    analyzed_at TEXT NOT NULL,
    marker_checked_at TEXT NOT NULL,
    result TEXT NOT NULL
);

CREATE TABLE star_names (
    name_key TEXT PRIMARY KEY,
    tic_id INTEGER NOT NULL,
    resolved_at TEXT NOT NULL
);

CREATE TABLE analyze_jobs (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    tic_id INTEGER NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'done', 'failed')),
    data_marker TEXT,
    steps TEXT NOT NULL DEFAULT '[]',
    error TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX analyze_jobs_status ON analyze_jobs (status, seq);
CREATE INDEX analyze_jobs_tic ON analyze_jobs (tic_id, status);

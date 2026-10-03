-- SQLite twin of ../0006_finder_only.sql (SQLite never had 0001's tables or ph_sep_deg as SQL).

DROP TABLE IF EXISTS event_sources;
DROP TABLE IF EXISTS events;
DROP TABLE IF EXISTS ingest_status;
DROP TABLE IF EXISTS star_analyses;
DROP TABLE IF EXISTS star_names;
DROP TABLE IF EXISTS analyze_jobs;
DROP TABLE IF EXISTS star_lightcurves;
DROP TABLE IF EXISTS known_planets;

ALTER TABLE candidates ADD COLUMN vetting TEXT;

CREATE TABLE monitor_runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT,
    finished_at TEXT,
    state TEXT NOT NULL CHECK (state IN ('running', 'done')),
    updated_at TEXT NOT NULL
);
CREATE INDEX monitor_runs_latest ON monitor_runs (state, started_at DESC, updated_at DESC);

CREATE TABLE monitor_shards (
    run_id TEXT NOT NULL REFERENCES monitor_runs (run_id) ON DELETE CASCADE,
    shard INTEGER NOT NULL,
    done INTEGER NOT NULL,
    total INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, shard)
);

CREATE TABLE monitor_stars (
    run_id TEXT NOT NULL REFERENCES monitor_runs (run_id) ON DELETE CASCADE,
    tic INTEGER NOT NULL,
    searched_at TEXT NOT NULL,
    outcome TEXT,
    detections_count INTEGER NOT NULL DEFAULT 0,
    record TEXT NOT NULL,
    PRIMARY KEY (run_id, tic)
);
CREATE INDEX monitor_stars_order ON monitor_stars (run_id, searched_at, tic);

CREATE TABLE monitor_seen (
    tic INTEGER PRIMARY KEY,
    run_id TEXT NOT NULL,
    searched_at TEXT NOT NULL,
    outcome TEXT,
    ra_deg REAL,
    dec_deg REAL,
    cell_ra INTEGER,
    cell_dec INTEGER,
    detections_count INTEGER NOT NULL DEFAULT 0,
    candidates_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX monitor_seen_newest ON monitor_seen (searched_at DESC, tic DESC);
CREATE INDEX monitor_seen_cell ON monitor_seen (cell_ra, cell_dec);

CREATE TABLE monitor_sectors (
    tic INTEGER NOT NULL REFERENCES monitor_seen (tic) ON DELETE CASCADE,
    sector INTEGER NOT NULL,
    PRIMARY KEY (tic, sector)
);
CREATE INDEX monitor_sectors_sector ON monitor_sectors (sector);

CREATE TABLE monitor_reasons (
    tic INTEGER NOT NULL REFERENCES monitor_seen (tic) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (tic, reason)
);

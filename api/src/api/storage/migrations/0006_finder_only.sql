-- Planet finder only (v2). Drops every table that served the removed parts of the site: sky
-- events (/events, /sky), Analyze a star and the per-star Lab (/lab), and the first prototype's
-- tables from 0001. Adds VET's vetting block to candidates, and the live monitor's tables.
-- docs/REMOVED.md lists what went with them.

DROP TABLE IF EXISTS events, event_sources, ingest_status CASCADE;
DROP TABLE IF EXISTS star_analyses, star_names, analyze_jobs CASCADE;
DROP TABLE IF EXISTS star_lightcurves, known_planets CASCADE;
DROP TABLE IF EXISTS traps, discoveries, catches, jobs CASCADE;
DROP FUNCTION IF EXISTS ph_sep_deg(DOUBLE PRECISION, DOUBLE PRECISION, DOUBLE PRECISION,
                                   DOUBLE PRECISION);

-- VET's "vetting" block from the candidate JSON, as ingested (NULL: not vetted by VET yet).
ALTER TABLE candidates ADD COLUMN vetting JSONB;

-- Monitor (/monitor/*): one row per sweep run (the GitHub run id). "running" while shards post
-- progress; "done" once finder_ingest has loaded the run's monitor/*.json.
CREATE TABLE monitor_runs (
    run_id TEXT PRIMARY KEY,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    state TEXT NOT NULL CHECK (state IN ('running', 'done')),
    updated_at TIMESTAMPTZ NOT NULL        -- last progress post or ingest: "live" goes stale
);
CREATE INDEX monitor_runs_latest ON monitor_runs (state, started_at DESC, updated_at DESC);

-- Each shard's own progress; a run's progress is the sum over its shards.
CREATE TABLE monitor_shards (
    run_id TEXT NOT NULL REFERENCES monitor_runs (run_id) ON DELETE CASCADE,
    shard INTEGER NOT NULL,
    done INTEGER NOT NULL,
    total INTEGER NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (run_id, shard)
);

-- Every star a run searched, with hunt's full monitor record (light curve included). Only the
-- last PH_MONITOR_KEEP_RUNS runs are kept.
CREATE TABLE monitor_stars (
    run_id TEXT NOT NULL REFERENCES monitor_runs (run_id) ON DELETE CASCADE,
    tic BIGINT NOT NULL,
    searched_at TIMESTAMPTZ NOT NULL,
    outcome TEXT,
    detections_count INTEGER NOT NULL DEFAULT 0,
    record JSONB NOT NULL,
    PRIMARY KEY (run_id, tic)
);
CREATE INDEX monitor_stars_order ON monitor_stars (run_id, searched_at, tic);

-- The latest search of every star ever searched (kept forever, small): the log, coverage and
-- stats. cell_ra/cell_dec index a 5-degree sky grid.
CREATE TABLE monitor_seen (
    tic BIGINT PRIMARY KEY,
    run_id TEXT NOT NULL,
    searched_at TIMESTAMPTZ NOT NULL,
    outcome TEXT,
    ra_deg DOUBLE PRECISION,
    dec_deg DOUBLE PRECISION,
    cell_ra INTEGER,
    cell_dec INTEGER,
    detections_count INTEGER NOT NULL DEFAULT 0,
    candidates_count INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX monitor_seen_newest ON monitor_seen (searched_at DESC, tic DESC);
CREATE INDEX monitor_seen_cell ON monitor_seen (cell_ra, cell_dec);

CREATE TABLE monitor_sectors (
    tic BIGINT NOT NULL REFERENCES monitor_seen (tic) ON DELETE CASCADE,
    sector INTEGER NOT NULL,
    PRIMARY KEY (tic, sector)
);
CREATE INDEX monitor_sectors_sector ON monitor_sectors (sector);

-- Detections rejected at the star's latest search, counted by reason.
CREATE TABLE monitor_reasons (
    tic BIGINT NOT NULL REFERENCES monitor_seen (tic) ON DELETE CASCADE,
    reason TEXT NOT NULL,
    n INTEGER NOT NULL,
    PRIMARY KEY (tic, reason)
);

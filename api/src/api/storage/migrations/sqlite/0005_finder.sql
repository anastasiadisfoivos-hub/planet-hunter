-- SQLite twin of ../0005_finder.sql.

CREATE TABLE candidates (
    id TEXT PRIMARY KEY,
    tic INTEGER NOT NULL,
    record TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0,
    radius_rjup REAL,
    period_d REAL,
    ephemeris_key TEXT NOT NULL,
    pixel_verdict TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'under review', 'dismissed', 'exported')),
    status_reason TEXT,
    votes_planet INTEGER NOT NULL DEFAULT 0,
    votes_fake INTEGER NOT NULL DEFAULT 0,
    votes_unsure INTEGER NOT NULL DEFAULT 0,
    votes_total INTEGER NOT NULL DEFAULT 0,
    known_checked_at TEXT,
    exported_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX candidates_score ON candidates (score DESC, id DESC);
CREATE INDEX candidates_newest ON candidates (created_at DESC, id DESC);
CREATE INDEX candidates_votes ON candidates (votes_total DESC, id DESC);
CREATE INDEX candidates_status ON candidates (status);

CREATE TABLE pixel_vets (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates (id) ON DELETE CASCADE,
    record TEXT,
    ephemeris_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('done', 'failed')),
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    vetted_at TEXT NOT NULL
);

CREATE TABLE votes (
    candidate_id TEXT NOT NULL REFERENCES candidates (id) ON DELETE CASCADE,
    voter_key TEXT NOT NULL,
    vote TEXT NOT NULL CHECK (vote IN ('planet', 'fake', 'unsure')),
    reason_chips TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (candidate_id, voter_key)
);

CREATE TABLE sensitivity (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    record TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE finder_sweep (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    record TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

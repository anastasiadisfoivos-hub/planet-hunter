-- Planet Finder (/finder): candidates from HUNT's nightly sweep, their pixel check (PIXELS),
-- people's votes, and the sweep's funnel and sensitivity. Filled by `python -m api.finder_ingest`.

-- One row per candidate "<tic>_<n>". `record` is HUNT's candidate JSON as ingested; the other
-- columns are copies of it (or of its vet and votes) kept for filtering and sorting.
CREATE TABLE candidates (
    id TEXT PRIMARY KEY,
    tic BIGINT NOT NULL,
    record JSONB NOT NULL,
    content_hash TEXT NOT NULL,            -- the record without created_at: unchanged = no rewrite
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    radius_rjup DOUBLE PRECISION,
    period_d DOUBLE PRECISION,
    ephemeris_key TEXT NOT NULL,           -- period/t0/duration/sectors the vet must match
    pixel_verdict TEXT,                    -- copy of pixel_vets.record->>'verdict'; NULL = unvetted
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'under review', 'dismissed', 'exported')),
    status_reason TEXT,
    votes_planet INTEGER NOT NULL DEFAULT 0,
    votes_fake INTEGER NOT NULL DEFAULT 0,
    votes_unsure INTEGER NOT NULL DEFAULT 0,
    votes_total INTEGER NOT NULL DEFAULT 0,
    known_checked_at TIMESTAMPTZ,          -- last re-check against TOI/CTOI/confirmed/EB lists
    exported_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
CREATE INDEX candidates_score ON candidates (score DESC, id DESC);
CREATE INDEX candidates_newest ON candidates (created_at DESC, id DESC);
CREATE INDEX candidates_votes ON candidates (votes_total DESC, id DESC);
CREATE INDEX candidates_status ON candidates (status);

-- The latest pixel check of a candidate. ephemeris_key identifies the period/t0/duration/sectors
-- it was run on: when HUNT changes those, the candidate is vetted again.
CREATE TABLE pixel_vets (
    candidate_id TEXT PRIMARY KEY REFERENCES candidates (id) ON DELETE CASCADE,
    record JSONB,                          -- PixelVet; NULL when state = 'failed'
    ephemeris_key TEXT NOT NULL,
    state TEXT NOT NULL CHECK (state IN ('done', 'failed')),
    error TEXT,
    attempts INTEGER NOT NULL DEFAULT 1,
    vetted_at TIMESTAMPTZ NOT NULL
);

-- One vote per voter per candidate; voting again replaces it. voter_key is the SHA-256 of the
-- browser's random X-Voter-Key, never the key itself.
CREATE TABLE votes (
    candidate_id TEXT NOT NULL REFERENCES candidates (id) ON DELETE CASCADE,
    voter_key TEXT NOT NULL,
    vote TEXT NOT NULL CHECK (vote IN ('planet', 'fake', 'unsure')),
    reason_chips JSONB NOT NULL DEFAULT '[]',
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (candidate_id, voter_key)
);

-- HUNT's injection-recovery sensitivity map: one row.
CREATE TABLE sensitivity (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    record JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

-- The latest sweep summary (GET /finder/funnel): one row.
CREATE TABLE finder_sweep (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    record JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

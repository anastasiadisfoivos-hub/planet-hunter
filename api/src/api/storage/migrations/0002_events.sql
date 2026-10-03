-- Live sky events (SHARED EVENT CONTRACT), written by `python -m api.ingest`, read by GET /events.
-- Filter columns are copied out of the record so every GET /events filter is an indexed predicate;
-- `record` is the Event exactly as served.

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    frame TEXT NOT NULL CHECK (frame IN ('sky', 'sun', 'earth')),
    observed_at TIMESTAMPTZ NOT NULL,
    ra_deg DOUBLE PRECISION,
    dec_deg DOUBLE PRECISION,
    confidence DOUBLE PRECISION NOT NULL,
    has_images BOOLEAN NOT NULL,
    from_latest_observed_window BOOLEAN NOT NULL DEFAULT false,
    record JSONB NOT NULL,
    source_hash TEXT NOT NULL,       -- the event as fetched, before pictures
    content_hash TEXT NOT NULL,      -- the stored record: an unchanged event is never rewritten
    images_checked_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);
-- Newest first, and the cursor (observed_at, id) that pages through it.
CREATE INDEX events_newest ON events (observed_at DESC, id DESC);
CREATE INDEX events_type ON events (type, observed_at DESC);
CREATE INDEX events_category ON events (category, observed_at DESC);
CREATE INDEX events_frame ON events (frame, observed_at DESC);
CREATE INDEX events_confidence ON events (confidence);
CREATE INDEX events_with_images ON events (observed_at DESC) WHERE has_images;
-- Region search: a declination band first, then the exact great-circle distance.
CREATE INDEX events_dec ON events (dec_deg) WHERE frame = 'sky';

-- Every source behind an event (a merged event has several), for the `sources` filter.
CREATE TABLE event_sources (
    event_id TEXT NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    PRIMARY KEY (source, event_id)
);
CREATE INDEX event_sources_event ON event_sources (event_id);

-- The last ingest run, each source's health, and Rubin's stream: one row per key.
CREATE TABLE ingest_status (
    key TEXT PRIMARY KEY,
    record JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
);

-- Great-circle distance in degrees (haversine), same formula as SQLite's registered function.
CREATE OR REPLACE FUNCTION ph_sep_deg(
    ra1 DOUBLE PRECISION, dec1 DOUBLE PRECISION, ra2 DOUBLE PRECISION, dec2 DOUBLE PRECISION
) RETURNS DOUBLE PRECISION LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT degrees(2 * asin(least(1.0, sqrt(
        sin(radians(dec2 - dec1) / 2) ^ 2
        + cos(radians(dec1)) * cos(radians(dec2)) * sin(radians(ra2 - ra1) / 2) ^ 2
    ))))
$$;

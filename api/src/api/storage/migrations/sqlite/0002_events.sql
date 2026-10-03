-- SQLite twin of ../0002_events.sql. Times are fixed-width ISO UTC text (they sort as times);
-- ph_sep_deg() is registered from Python.

CREATE TABLE events (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    category TEXT NOT NULL,
    frame TEXT NOT NULL CHECK (frame IN ('sky', 'sun', 'earth')),
    observed_at TEXT NOT NULL,
    ra_deg REAL,
    dec_deg REAL,
    confidence REAL NOT NULL,
    has_images INTEGER NOT NULL,
    from_latest_observed_window INTEGER NOT NULL DEFAULT 0,
    record TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    images_checked_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX events_newest ON events (observed_at DESC, id DESC);
CREATE INDEX events_type ON events (type, observed_at DESC);
CREATE INDEX events_category ON events (category, observed_at DESC);
CREATE INDEX events_frame ON events (frame, observed_at DESC);
CREATE INDEX events_confidence ON events (confidence);
CREATE INDEX events_with_images ON events (observed_at DESC) WHERE has_images;
CREATE INDEX events_dec ON events (dec_deg) WHERE frame = 'sky';

CREATE TABLE event_sources (
    event_id TEXT NOT NULL REFERENCES events (id) ON DELETE CASCADE,
    source TEXT NOT NULL,
    PRIMARY KEY (source, event_id)
);
CREATE INDEX event_sources_event ON event_sources (event_id);

CREATE TABLE ingest_status (
    key TEXT PRIMARY KEY,
    record TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

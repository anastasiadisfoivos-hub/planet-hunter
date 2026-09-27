-- SQLite twin of ../0008_runner.sql.
CREATE TABLE monitor_heartbeat (
    id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    record TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

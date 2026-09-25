-- SQLite twin of ../0004_stardata.sql.

CREATE TABLE star_lightcurves (
    tic_id INTEGER PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('stored', 'no_data')),
    data_marker TEXT,
    stored_at TEXT NOT NULL,
    curve TEXT
);

CREATE TABLE known_planets (
    tic_id INTEGER PRIMARY KEY,
    host_name TEXT,
    star TEXT NOT NULL,
    planets TEXT NOT NULL,
    fetched_at TEXT NOT NULL
);

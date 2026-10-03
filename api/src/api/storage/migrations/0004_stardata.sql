-- Per-star Lab (/lab/star/<tic>). Kept out of star_analyses so GET /stars/{tic}/analysis stays
-- small. Rows here are filled going forward: a star analyzed before 0004 gets its light curve
-- re-read (not re-searched) the next time it is analyzed.

-- The unfolded light curve, binned to <= 3000 points; or the fact that MAST has none.
CREATE TABLE star_lightcurves (
    tic_id BIGINT PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('stored', 'no_data')),
    data_marker TEXT,
    stored_at TIMESTAMPTZ NOT NULL,
    curve JSONB                            -- {time_btjd[], flux[], binned_from, sectors[]}
);

-- NASA Exoplanet Archive (pscomppars) per TIC, cached; planets = '[]' for a star with none.
CREATE TABLE known_planets (
    tic_id BIGINT PRIMARY KEY,
    host_name TEXT,
    star JSONB NOT NULL,                   -- {mass_msun, radius_rsun, teff_k, distance_pc, tmag}
    planets JSONB NOT NULL,                -- [{name, period_d, a_au, radius, mass, mass_kind}]
    fetched_at TIMESTAMPTZ NOT NULL
);

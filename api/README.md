# api/: planet-hunter phenomena spotter API

A FastAPI service with two jobs:
- **Live sky events**: supernovae, near-Earth objects, solar flares, fireballs, gamma-ray bursts
  and the rest, with real pictures, filtered for the 3D map.
- **Analyze a star**: checks any star for planets in NASA TESS data.

There are no accounts, traps, forecasts or points.

- Events use the SHARED EVENT CONTRACT, which lives in
  [events/src/skyevents/models.py](../events/src/skyevents/models.py).
- `Image.thumb_url` and the `forecast_map` kind come from [images/](../images/README.md).

```sh
uv sync
uv run pytest -q                                   # fakes; every storage test on SQLite AND Postgres
uv run uvicorn --factory api.app:create_app        # serve on :8000, docs at /docs
uv run python -m api.ingest                        # fetch events + pictures into the database
uv run python -m api.precompute --known-systems    # pre-compute Analyze results (PH_ADAPTERS=real)
```

## Endpoints

| Method | Path | Query / body | Returns |
|---|---|---|---|
| GET | `/events` | filters below, `cursor`, `limit` ≤ 200 (default 50) | `{items: [Event], next_cursor}`, newest `observed_at` first |
| GET | `/events/{id}` | | `Event` (404 once older than 90 days) |
| GET | `/status` | | `{ingested_at, window, events_stored, ingest, sources: {name: {state, live, last_event_at, events, error, …}}, rubin_stream}` |
| POST | `/analyze` | `{"name": "WASP-18"}` or `{"tic_id": 100100827}` | **200** `{status: "done", cached: true, result}` when a current result is stored, else **202** `{status: "queued", job_id, queue_position}` |
| GET | `/jobs/{id}` | | `{status, queue_position, steps: [{name, at}], error, result}` |
| GET | `/stars/{tic}/analysis` | | the stored result `{tic_id, data_marker, analyzed_at, marker_checked_at, analysis}` |
| GET | `/healthz` | | `{ok: true}` |

**`/events` filters.** All are optional and they combine with AND. List filters take either
`a,b` or a repeated parameter (`?types=a&types=b`).

- `types`: event types from the contract.
- `categories`: `transients`, `solar_system`, `sun_space_weather`, `earth_atmosphere`,
  `high_energy`, `other`.
- `since` / `until`: filter on `observed_at`; ISO time or an age like `7d`.
- `sources`: a merged event matches if any of its sources matches.
- `frame`: `sky`, `sun` or `earth`.
- `ra`, `dec`, `radius`: a region in degrees; sky events only.
- `min_confidence`.
- `has_images`.
- `include_latest_window`: defaults to false. While Rubin's stream is paused, the feed carries
  Rubin's latest real nights at their true dates, marked `raw.from_latest_observed_window`.
  These events are left out unless you set this to true.

Unknown values give 422.

**`POST /analyze`** (deploy/HOSTING.md R1–R5):

1. **Resolve the name.** Accepted forms, in order:
   - `TIC 123`;
   - a Known system (`WASP-18`, `wasp 18 b`, …);
   - a name resolved before (kept in `star_names`);
   - otherwise MAST resolves it (404 if no star has that name).
2. **Stored result checked within `PH_MARKER_TTL_S`** (6 h): the API serves it without any
   network call.
3. **Otherwise the API asks MAST for the star's newest TESS sector** (the data marker):
   - **Marker unchanged:** it serves the stored result and resets the TTL.
   - **MAST down or slow** (`PH_MARKER_TIMEOUT_S`): it serves the stored result with
     `note: "data check unavailable: showing stored result"`.
   - **No TESS data:** 404.
   - **New data, or no stored result:** it queues a job and returns 202.
4. **How jobs run:**
   - At most `PH_MAX_CONCURRENT_HUNTS` (2) run at once; the rest wait in order.
   - One job per star: concurrent requests for a star get the same `job_id`, so it is hunted
     once.
   - Before hunting, the job re-checks storage, in case a precompute shard stored the same data
     meanwhile.

A result holds:
- the star;
- the sectors used;
- each signal: type (best guess), confidence, period, depth, duration, size, known-catalogue
  match, the vetting checks in plain English, and the light curve **folded on the period,
  binned to ≤ 1000 points**;
- up to 50 flares;
- a one-paragraph summary.

A stored result is about 20 KB.

## Pre-compute

```sh
PH_ADAPTERS=real uv run python -m api.precompute --tic-file ../web/public/data/hosts.json --shard 3/20
PH_ADAPTERS=real uv run python -m api.precompute --known-systems [--force]
```

- **Input:** `--tic-file` reads `hosts.json` (its `tic` column), a JSON list, or one TIC per
  line.
- **Sharding:** `--shard i/N` (0-based) takes every N-th star of the sorted list, so N runs
  cover it exactly once.
- **Idempotent:** a star whose stored marker is current is skipped; `--force` re-analyzes it.
- **Failures:** a failure is recorded and the run continues. Stars with no TESS data are
  counted as `no_data`, not as failures.
- **Output and exit code:** prints a JSON summary. Exits 1 when more than
  `--max-failed-fraction` of the stars failed (default: any).
- **`--time-budget-min`:** stops starting new stars after that many minutes, so a CI job ends
  cleanly; the next run picks up the rest.

[ci/precompute.yml](ci/precompute.yml) runs this as 20 GitHub Actions shards over the 1,748 map
hosts, after a Known-systems job. [ci/ingest.yml](ci/ingest.yml) runs `api.ingest` hourly.
Both need the `PH_DATABASE_URL` secret; DEPLOY moves them to `.github/workflows/`.

## Ingest

`python -m api.ingest [--since 7d] [--sources a,b] [--no-pictures] [--keep-days 90]` runs these
steps:

1. Runs `skyevents.ingest` (every source, de-duplicated).
2. Adds pictures with `skypictures` (every URL checked).
3. Upserts into `events`.
4. Deletes events observed more than 90 days ago.
5. Stores each source's status and `skysources.stream_status()` for `/status`.

Details:
- **Upserts:** an event whose content hasn't changed is not rewritten.
- **Pictures:** an unchanged event keeps its stored pictures for `--pictures-ttl-h` (24 h), so
  hourly runs don't re-check every URL.
- **Honesty rule:** "new planet" and "discovered" are rewritten on the way in. This covers
  every string except `raw` and URLs. The tests scan every JSON response for both phrases.
- **Offline replay:** `--from-file events.json --status-file status.json` stores an
  `events-ingest` output without fetching anything.

## Configuration (env)

| Variable | Default | What it sets |
|---|---|---|
| `PH_DATABASE_URL` | none | Postgres URL; when set, used instead of SQLite |
| `PH_DB_PATH` | `spotter.db` | SQLite file (when `PH_DATABASE_URL` is unset) |
| `PH_DB_POOL_MAX` / `PH_DB_TIMEOUT_S` / `PH_DB_STATEMENT_TIMEOUT_MS` | `5` / `5` / `15000` | Postgres pool |
| `PH_ADAPTERS` | `fake` | `real` uses pipeline/ for Analyze |
| `PH_WEB_ORIGIN` | none | CORS: the web app's origin (comma-separated for several) |
| `PH_TRUSTED_PROXY_HOPS` | `0` | proxies appending to X-Forwarded-For (Render: `1`); `0` uses the socket address |
| `PH_RATE_READ_PER_MIN` | `120` | GET requests per IP per minute |
| `PH_RATE_ANALYZE_PER_MIN` | `6` | POST /analyze per IP per minute |
| `PH_MAX_CONCURRENT_HUNTS` | `2` | analyses running at once (Render Free: `1`) |
| `PH_MAX_QUEUED_JOBS` | `50` | queued + running stars; above it POST /analyze is 503 |
| `PH_HUNT_TIMEOUT_S` | `600` | one analysis |
| `PH_MARKER_TTL_S` | `21600` | ask MAST for a star's newest sector at most this often |
| `PH_MARKER_TIMEOUT_S` | `10` | that question, inside POST /analyze |
| `PH_RESOLVE_TIMEOUT_S` | `20` | resolving a star name through MAST |

## Storage

The two backends have the same tables and keys:
- **SQLite** (dev, tests) applies `src/api/storage/migrations/sqlite/*.sql`.
- **Postgres** (prod, e.g. Supabase through its connection pooler) applies
  `src/api/storage/migrations/*.sql`, in order and under an advisory lock.

Migrations run on startup of the API, ingest and precompute. To change the schema, add the next
numbered file to both folders; never edit one that has been applied.

| Migration | Tables |
|---|---|
| `0001_init` (Postgres only) | traps, discoveries, catches, jobs. No longer used; kept so applied databases stay consistent |
| `0002_events` | `events`: `id` PK, `type`, `category`, `frame`, `observed_at`, `ra/dec` (nullable), `confidence`, `has_images`, `from_latest_observed_window`, `record` jsonb, plus content hashes. It also creates `event_sources`, `ingest_status` and `ph_sep_deg()`. An index backs every filter |
| `0003_analyze` | `star_analyses` (one row per TIC: `data_marker`, `analyzed_at`, `marker_checked_at`, `result`), `star_names`, `analyze_jobs` |

`uv run pytest` runs every storage-touching test on both backends. Postgres comes from
`PH_TEST_DATABASE_URL`, a throwaway database that the tests wipe. If that's unset, it comes from a
disposable `postgres:16` Docker container. `PH_TEST_BACKENDS=sqlite` (or `postgres`) runs just
one backend.

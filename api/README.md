# api/: planet-hunter traps API

A FastAPI service for EXPLORE mode. Anonymous players place traps (a sky sphere or a TESS star) and collect what those traps catch. There are no points.
The shared shapes are defined in [contracts/CONTRACT.md](../contracts/CONTRACT.md) and the ID rules in [contracts/CONVENTIONS.md](../contracts/CONVENTIONS.md).

```sh
uv sync
uv run pytest -q                                   # tests (fakes), on SQLite and Postgres
uv run uvicorn --factory api.app:create_app        # serve on :8000, docs at /docs
uv run python -m api.nightly [--db PATH | --database-url URL] [--dry-run]
uv run python -m api.export_schemas                # regenerate contracts/schemas/*.json
```

Every request needs an `X-Player-Id: <uuid>` header.

## Endpoints

| Method | Path | Body / query | Returns |
|---|---|---|---|
| POST | `/traps` | `{"sphere": Sphere}` or `{"star": StarTarget}` | 201 `{trap, sweep, catches: [Discovery], job_id}` |
| GET | `/traps` | | `[Trap]` |
| DELETE | `/traps/{id}` | | 204 (the player keeps its catches) |
| GET | `/forecast` | `ra, dec, radius, window=7d` | `Forecast` |
| POST | `/hunt` | `{"star": StarTarget}` | 202 `{job_id, status}` |
| GET | `/jobs/{id}` | | `{status, queue_position, steps, result, error, …}` |
| GET | `/discoveries` | `limit≤100, cursor` | `{items: [Discovery], next_cursor}`, most recently caught first |
| GET | `/discoveries/{id}` | | `Discovery` |

- A sky trap is swept right away: the last 7 nights of Rubin alerts, subject to a timeout, with the results returned in the response.
- A star trap queues a TESS hunt and returns its `job_id`.
- At most 2 hunts run at once (`PH_MAX_CONCURRENT_HUNTS`); the rest wait in order.

## Configuration (env)

| Variable | Default | What it sets |
|---|---|---|
| `PH_DATABASE_URL` | none | Postgres URL; when set, used instead of SQLite |
| `PH_DB_PATH` | `traps.db` | SQLite file (when `PH_DATABASE_URL` is unset) |
| `PH_DB_POOL_MAX` | `5` | Postgres connections per process |
| `PH_DB_TIMEOUT_S` | `5` | connect timeout, and max wait for a free pooled connection |
| `PH_DB_STATEMENT_TIMEOUT_MS` | `15000` | per-statement limit on the server |
| `PH_ADAPTERS` | `fake` | `fake` or `real` |
| `PH_CORS_ORIGINS` | none | comma-separated allowed origins |
| `PH_RATE_*_PER_MIN` | | rate limits per player and per IP |
| `PH_MAX_TRAPS_PER_PLAYER` | `50` | trap cap per player |
| `PH_MAX_PENDING_JOBS_PER_PLAYER` | `3` | queued or running hunts per player |
| `PH_SWEEP_TIMEOUT_S` | | instant-sweep timeout |
| `PH_HUNT_TIMEOUT_S` | | hunt timeout |

## Swapping fakes for real modules

The API reaches the other folders only through the Protocols in `src/api/ports.py`:

| Port | Provided by | Method |
|---|---|---|
| `AlertSource` | sources/ | `alerts_in_sphere(sphere, since, until)` |
| `StarHunter` | pipeline/ | `latest_data_marker(tic)` and `hunt(tic, progress)` |
| `Forecaster` | forecast/ | `forecast(sphere, start, end)` |
| `Storage` | api/: `storage/sqlite.py` or `storage/postgres.py` | |

To replace a fake:
1. Add the sibling as a uv path dependency.
2. Implement its factory in `src/api/adapters/real.py`.
3. Add that adapter to the parameter lists in `tests/test_ports_conformance.py`.
4. Run with `PH_ADAPTERS=real`.

Nothing else changes. The API assigns the final TESS signal IDs itself (period matching), so pipeline/ doesn't need to know what has already been stored.

## Storage

SQLite is the default (local dev, tests). Set `PH_DATABASE_URL` and the API and the nightly
checker both use Postgres instead, e.g. a free Supabase project, so data survives the host
wiping its disk.

- **Supabase:** Project Settings → Database → Connection string → *Connection pooler*, either
  mode (session, port 5432, or transaction, port 6543; the direct host is IPv6-only). Use it
  as-is, including `?sslmode=require` if present.
- **Migrations** are the plain SQL files in `src/api/storage/migrations/`, applied in name order on
  startup (API and nightly alike), each once, recorded in `schema_migrations`, under an advisory
  lock so two processes starting together don't race. To change the schema, add `0002_*.sql`;
  never edit an applied file.
- **Keys** are the same as SQLite's, so re-runs stay idempotent (`ON CONFLICT DO NOTHING` on the
  one-catch-per-player key, upserts on discovery IDs).
- **Sharing:** the API and the nightly checker write concurrently (MVCC, no global write lock).
  Assigning TESS signal IDs for a star takes a per-star advisory lock for its transaction, so
  two hunts of one star can't hand out the same ID.
- **Accounts later:** `player_id` is a plain text column everywhere; nothing assumes it's a UUID.

Tests run every storage-touching test on both backends. Postgres comes from
`PH_TEST_DATABASE_URL` (a throwaway database; the tests wipe it) or, if that's unset, a
disposable `postgres:16` Docker container. Without either, the Postgres cases are skipped.
`PH_TEST_BACKENDS=sqlite` (or `postgres`) runs just one.

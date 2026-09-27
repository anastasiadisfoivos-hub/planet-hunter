# api/: planet-hunter planet finder API

A FastAPI service for the Planet Finder, and nothing else (v2: sky events, Analyze a star and
the Lab were removed; [docs/REMOVED.md](../docs/REMOVED.md) lists what went). Two parts:
- **Planet Finder**: the nightly sweep's planet *candidates*, their pixel check and vetting,
  people's votes, and the ExoFOP export. See **Planet Finder** below.
- **Monitor**: what the sweep is searching right now (or a replay of last night), the search
  log, sky coverage and totals. See **Monitor** below.

There are no accounts. The wording is always "candidate", never "new planet" or "discovered"
([honesty.py](src/api/honesty.py); every test response is scanned for it).

```sh
uv sync
uv run pytest -q                                   # fakes; every storage test on SQLite AND Postgres
uv run uvicorn --factory api.app:create_app        # serve on :8000, docs at /docs
uv run python -m api.migrate                       # apply migrations to PH_DATABASE_URL (else SQLite) and exit
docker build -t planet-hunter-api . && docker run --rm -p 8000:8000 planet-hunter-api   # the Render image
uv run --extra finder python -m api.finder_ingest --dir ../sweep/candidates --run-id 123
```

## Endpoints

| Method | Path | Query / body | Returns |
|---|---|---|---|
| GET | `/finder/candidates` | filters below, `sort`, `cursor`, `limit` ≤ 200 (default 50) | `{items: [candidate summary], next_cursor}` |
| GET | `/finder/candidates/{id}` | header `X-Voter-Key` (optional) | `{candidate, pixel_vet, votes, my_vote}` |
| POST | `/finder/candidates/{id}/vote` | header `X-Voter-Key`; `{"vote": "planet"\|"fake"\|"unsure"\|null, "reason_chips": [...]}` | `{id, vote, reason_chips, previous_vote, status, votes}` |
| GET | `/finder/funnel` | | `{sweep_at, stages: [{stage, count, source}], by_status, by_pixel_verdict}` |
| GET | `/finder/sensitivity` | | `{updated_at, sensitivity}` (404 until one is stored) |
| POST | `/finder/export/ctoi` | `Authorization: Bearer <PH_ADMIN_TOKEN>`; `{ids, tag?, paper_url?}` | ExoFOP CTOI upload file (text) |
| GET | `/monitor/now` | `after` (replay: the star after this tic) | `{mode: "live"\|"replay", run_id, run_started_at, progress: {done, total}, star, next_at, next_tic, label, runner}` |
| GET | `/monitor/stars/{tic}` | | the star's latest stored record (404 once pruned) |
| GET | `/monitor/sparks` | | `{unit, bins, note, stars: {tic: [ppm, ...]}}` |
| GET | `/monitor/coverage/queues` | | `{updated_at, queues: {name: {done, listed, running}}}` |
| GET | `/monitor/log` | `limit` 1–200 (default 50) | `{items: [{tic, outcome, detections_count, searched_at}]}`, newest first |
| GET | `/monitor/coverage` | | `{stars_searched_total, by_sector: [{sector, stars}], cell_deg, sky_cells: [{ra, dec, stars}]}` |
| GET | `/monitor/stats` | | `{stars_searched, signals, candidates, rejected_by_reason: {reason: n}, last_run_at}` |
| POST | `/monitor/progress` | `Authorization: Bearer <PH_INGEST_TOKEN>`; `{run_id, run_started_at?, shard, done, total, star?, label?}` | `{run_id, state, progress: {done, total}}` |
| POST | `/monitor/heartbeat` | ingest token; `{state, runner_id?, run_id?, next_run_at?, queues?}` | `{ok, received_at}` |
| POST | `/finder/ingest` | ingest token; `{run_id, run_started_at?, candidates: [{id, candidate}], monitor: [record], summary?, sensitivity?, final}` | the chunk's summary |
| GET | `/finder/pixel-queue` | ingest token; `limit` ≤ 100, `max_attempts` | `{items: [{id, ephemeris_key, candidate}]}` |
| POST | `/finder/candidates/{id}/pixel-vet` | ingest token; `{ephemeris_key, vet \| error}` | `{id, state}` |
| GET | `/healthz` | | `{ok: true}` |

## Planet Finder

HUNT's nightly sweep (hunt/) writes candidates `candidates/<tic>_<n>.json` (`n` is the signal
number, or `s<m>` / `d<m>` for a single / duo dip, e.g. `150428135_s1`); PIXELS
(pixels/, `vet_pixels`) checks whether each dip is on the target star. This API stores both,
takes votes, and exports chosen candidates for ExoFOP. The wording is always "candidate".

**`python -m api.finder_ingest --dir <candidates> [--sensitivity FILE] [--summary FILE]
[--monitor-dir DIR --run-id ID --run-started-at ISO]`**
1. Upserts every `<tic>_<n>.json`. A missing or empty `--dir` is an empty night: nothing to
   upsert, but the summary and the monitor's stars are still loaded and the exit code is 0.
   `period_d` may be `null` (a single dip); such a candidate is never pixel-checked or re-checked
   against the lists, which both need a period. A file whose content (ignoring `created_at`) is unchanged is
   not rewritten. Status and votes are never touched. Invalid files are listed in the summary
   and the exit code is 1; the valid ones are still stored.
2. **Dismissal on re-check.** An open candidate (`new` / `under review`) that is now on a TOI,
   CTOI, confirmed-planet or eclipsing-binary list becomes `dismissed`, with `status_reason`
   (e.g. `matches TOI TOI-1234.01 (same period)`). Two sources:
   - the candidate's own `known_lists` (from HUNT). Accepted shapes: a list of matches
     `[{list, name, alias?}]` (entries with `matched: false` don't count), a `hunter.known.check`
     result `{status: "known", list_name, name, alias}`, or `{list: [matches]}`;
   - a re-check of up to `--recheck-limit` open candidates, the longest-unchecked first, through
     `hunter.known.check(..., include_eb_catalogue=True)` (period within 1% or ×2, ×3, ½, ⅓).
     If the lists can't be reached, the candidate stays open and is re-checked next run.
   Exported candidates are never dismissed: once submitted, they are on the CTOI list.
3. Stores the sweep summary (`--summary`, else `summary.json` or `sweep_summary.json` in the
   folder or one folder up) and `--sensitivity`.
4. Loads the run's monitor stars; see **Monitor** below.
5. Pixel-checks up to `--pixel-limit` (20) open candidates with no vet for their current
   period/t0/duration/sectors: never-vetted first, then by score. It stops starting new ones
   after `--time-budget-min` (30). A failure is stored and retried on later runs, at most
   `--max-vet-attempts` (3) times per ephemeris. If a candidate's ephemeris changes, it is
   vetted again. When pixels/ isn't installed, the rest still runs and the summary says
   `pixels.unavailable`.

Pixel checks use pixels/ (package `skypixels`), which is an optional extra so that the web API's
deploy doesn't pull in astropy or lightkurve: `uv sync --extra finder`. The adapter runs
`vet_pixels` with a temporary `out_dir` and builds `images` from the per-sector
`tic<id>_s<sector>_pixels.json`: `{out_of_transit, difference, markers}` of the first sector,
plus `sector` and every sector's full web JSON in `images.per_sector`. A stored vet is about
25 kB, or up to about 250 kB in a crowded field (`neighbours` lists every Gaia star within 2.5′).

`--no-pixels` / `--no-recheck` skip steps 5 / 2b. The Oracle Cloud server that runs the sweep runs this
after each sweep, with `PH_ADAPTERS=real` and `uv sync --extra finder` (see [docs/DEPLOY.md](../docs/DEPLOY.md)).

**`GET /finder/candidates` filters** (they combine with AND; lists take `a,b` or repeated parameters):
- `min_radius` / `max_radius` (Jupiter radii);
- `min_period` / `max_period` (days);
- `pixel_verdict`: `on target`, `possible neighbour`, `off target`, `inconclusive`,
  `unvetted` (`on_target` works too);
- `status`: `new`, `under review`, `dismissed`, `exported`. The default is all but `dismissed`;
- `needs_votes=true`: open candidates with fewer than `PH_FINDER_VOTES_NEEDED` votes.

`sort` is `score` (default), `newest` (first ingested, from the candidate's `created_at`) or
`votes`, always descending. A `cursor` only works with the sort that made it. Each item is the
candidate's `tic, kind, period_d, t0_btjd, duration_h, depth_ppm, snr, sde, n_transits, sectors,
radius_rjup, radius_low, radius_high, radius_rjup_best, known_lists, score_parts` (no curves, no
checks), plus `id, score, checks_passed, checks_total, pixel_verdict, status, status_reason,
votes: {planet, fake, unsure, total}, created_at, updated_at`. `checks_total` counts the checks
that ran (`passed` true or false); `checks_passed` those that passed.

The radius filters use one number per candidate: `radius_rjup_best`, else `radius_rjup` when it is
a number, else the middle of `radius_low`..`radius_high` (hunt writes `radius_rjup` as the
`[low, high]` range).

**`GET /finder/candidates/{id}`** returns:
- `candidate`: the full JSON plus status fields, including `vetting`: VET's block from the
  candidate JSON, stored as JSON exactly as given (honesty rule applied), or `null`. Any JSON
  object is accepted; anything else makes the file invalid;
- `pixel_vet`: the PixelVet plus `vetted_at`, and `current: false` when the ephemeris changed
  since the vet ran; `null` if it was never vetted;
- `votes`: the tallies plus `reasons: {vote: {chip: count}}`;
- `my_vote`: the vote of the sender's `X-Voter-Key`, or `null`.

**Votes.** There are no accounts. The browser makes a random `X-Voter-Key` (16–128 of
`A-Za-z0-9_-`) once and sends it. Only its SHA-256 is stored. Each key gets one vote per
candidate; voting again replaces the vote and `previous_vote` says what it was. Reason chips are
up to 8 slugs (`a-z0-9_-`, ≤ 40 characters), lower-cased and de-duplicated. The first vote moves a
`new` candidate to `under review`. `{"vote": null}` withdraws the sender's vote (`reason_chips`
are ignored; withdrawing when there is no vote is a no-op); when the last vote goes, an `under
review` candidate is `new` again. Casting on a dismissed candidate answers 409; withdrawing
works. Votes are limited per IP
(`PH_RATE_VOTE_PER_MIN`), in a bucket separate from reads, so new keys don't get around it.

**Export for ExoFOP.** `POST /finder/export/ctoi {ids, tag?, paper_url?}` needs
`Authorization: Bearer <PH_ADMIN_TOKEN>` (compared in constant time). Answers:
- **404** when `PH_ADMIN_TOKEN` is unset;
- **403** when the header is missing or wrong, or not `Bearer`;
- **404 / 409** when an id is unknown / dismissed;
- **422** `{reason: "Dip comes from a neighbour; not exportable", ids}` when a candidate's pixel
  verdict is `off target`;
- **422** `{reason: "Single or duo dip: ExoFOP needs one period and a planet number; not
  exportable", ids}` for `<tic>_s<m>` / `<tic>_d<m>` ids.

Any refusal exports and marks nothing. Candidates whose pixel check was `inconclusive`, or that
haven't been checked yet, can still be exported; their notes say `pixel check inconclusive` or
`no pixel check yet`. It returns ExoFOP-TESS's **bulk planet-parameter upload**
file, `params_planet_YYYYMMDD_001.txt`. The format is documented in ExoFOP's template
<https://exofop.ipac.caltech.edu/tess/templates/params_planet_YYYYMMDD_001.txt>, linked from
<https://exofop.ipac.caltech.edu/tess/help.php> under "Bulk Parameter Upload":
- **Delimiter and columns:** pipe-delimited, not commas. The 46 columns are in the template's
  order, spellings included.
- **Rows:** one `flag=newctoi`, `disp=PC` row per candidate:
  - `target` = `TIC<tic>.<nn>`;
  - `epoch` = BTJD + 2457000;
  - `period`, `depth`, `duration`;
  - `radius` in Earth radii (R_J = 11.209 R_⊕);
  - `prop_period` = 0;
  - `notes` ≤ 120 characters, always stating the pixel check.
- **Comment lines:** lines starting with `\` are comments that ExoFOP ignores.

The candidates are marked `exported`. The owner uploads the file by hand. Before uploading:
- **Paper URL:** ExoFOP's candidate guidelines
  (<https://exofop.ipac.caltech.edu/tess/candidate_help.php>) require the URL of a published,
  refereed paper for every new CTOI. The file has a warning comment when `paper_url` is empty.
- **`.nn` suffix:** each target must use the TIC's next free `.nn` on ExoFOP.

## Monitor

A **star** is hunt's `monitor/<tic>.json` (DEEPHUNT writes one per star searched):

```
{tic, tmag, teff, radius_rsun, ra, dec, sectors, observed_from, observed_to,
 lightcurve: {t, f},
 detections: [{t0, duration_h, depth_ppm, period_d|null, kind, outcome, reason}],
 outcome, searched_at}
```

The API stores it as given (honesty rule applied, NaN/inf as `null`, `searched_at` normalised to
ISO UTC) and requires only `tic` (a positive integer); `detections` and `sectors` must be lists
when present. It counts on these fields:
- a detection whose `outcome` is `"candidate"` counts as a candidate; every other detection is
  rejected, counted under its `reason` (else its `outcome`, else `unknown`);
- `ra`/`dec` place the star in a 5° sky cell; `sectors` count it in each sector.

**Where stars come from.**
1. While a sweep runs, each shard may `POST /monitor/progress` with
   `Authorization: Bearer <PH_INGEST_TOKEN>` and `{run_id, run_started_at?, shard, done, total,
   star?}`: its own progress (the run's progress is the sum over shards) and, optionally, the star
   it just finished. `run_id` is the sweep's GitHub run id (1–64 of `A-Za-z0-9_.:-`). The first
   post creates the run as `running`. With `PH_INGEST_TOKEN` unset the endpoint is 404; a wrong
   token is 403. It has its own per-IP bucket (`PH_RATE_INGEST_PER_MIN`).
2. After the sweep, `finder_ingest` loads every `monitor/<tic>.json` (from `--monitor-dir`, else
   `monitor/` next to or inside `--dir`) as run `--run-id` and marks the run `done`. Invalid
   files are reported like invalid candidates. A finished run never goes back to `running`. Only
   the newest `PH_MONITOR_KEEP_RUNS` (3) finished runs keep their stars (the records carry light
   curves); each star's latest search is kept forever for the log, coverage and stats.

**`GET /monitor/now`.**
- `"live"` while a run is `running` and a shard posted within `PH_MONITOR_LIVE_TIMEOUT_S` (900 s).
  `star` is the run's most recently searched star (`null` until a shard posts one); `progress`
  is the shards' sum; `next_at` is `null`.
- `"replay"` otherwise: the newest finished run with stars (else any run with stars), in search
  order (`searched_at`, then `tic`), one star per `PH_MONITOR_STEP_S` (20 s) of server time:
  star number `floor(unix_time / 20) mod stars`. Every viewer sees the same star at the same
  moment. `next_at` is when it moves on; `progress` is the run's final count (the larger of the
  shards' `done` and the stars loaded). With no runs at all: `run_id`, `star`, `next_at` are
  `null` and `progress` is `{done: 0, total: 0}`.

**`GET /monitor/log`, `/coverage`, `/stats`** read each star's latest search:
- `log`: newest first;
- `coverage`: `by_sector` in sector order; `sky_cells` are 5°×5° cells (`cell_deg: 5`) with
  `ra`/`dec` at the cell's centre, only cells with stars, stars without coordinates left out;
- `stats`: `signals` = detections, `candidates` = detections with outcome `candidate`,
  `rejected_by_reason` = the rest, `last_run_at` = the newest run's start (else its last update).

**Additions for the web's monitor** (all additive; the fields above are unchanged; migration
`0007_monitor_detail` adds `monitor_seen.known_count`/`rejected_count`, backfilled from the kept
records, and an index on `monitor_stars (tic, searched_at DESC)`):
- `GET /monitor/now?after=<tic>` (replay only; ignored live): the star after `<tic>` in the
  replayed run's search order, wrapping around; a tic not in the run gives the first star. Every
  answer has `next_tic`: in replay the star after the returned one (wrapping; with one star, the
  same tic), `null` live or with no run. `next_at` is still the server-timed slot.
- `GET /monitor/stars/{tic}`: the star's latest stored record (full, light curve included), from
  any kept run; 404 once no kept run has it.
- `GET /monitor/log?detail=true`: each item also has `record`, its latest search's record without
  `lightcurve` (`null` once that run is pruned). Without `detail` the items are unchanged.
- `GET /monitor/coverage` adds `stars: [{tic, ra, dec, outcome, sectors}]`, every star ever
  searched (its latest search), by tic; `ra`/`dec` are exact degrees or `null`, `sectors`
  ascending. One row per star (one query); tens of thousands of stars is fine for now.
- `GET /monitor/stats` adds `known` and `rejected`: detections whose outcome is exactly `known` /
  `rejected` (stars searched before 0007 whose record was already pruned count 0). Note that
  `rejected_by_reason` still covers every non-candidate detection, known ones included.
  `funnel` (only when a sweep summary is stored): `[{key, label, count}]` for `stars`,
  `signals`, `snr`, `sde`, `checks`, `candidates` from the summary's `stars_searched`,
  `signals_found`, `after_snr`, `after_sde`, `after_checks`, `candidates`.
- `GET /monitor/sparks` (`Cache-Control: public, max-age=300`): `{unit: "ppm", bins: 180, note,
  stars: {"<tic>": [int, ...]}}` for every star whose latest search's record (with a light
  curve) is kept: `lightcurve.f` joined end to end (non-numbers dropped), split by point index
  into 180 bins (`numpy.linspace(0, n, 181).astype(int)` edges; fewer when n < 180), each
  `round((min - 1) * 1e6)`. Computed per request from the kept records.

## The search server over HTTP

The search server (runner/) needs no database URL: it holds only the API's address and
`PH_INGEST_TOKEN`, and everything it writes goes through these token-protected routes (404 while
`PH_INGEST_TOKEN` is unset, 403 with a wrong token, off the OpenAPI page).

**`python -m api.remote_ingest --api-url URL --dir RUN/candidates [--monitor-dir DIR] [--summary
FILE] [--sensitivity FILE] --run-id ID [--run-started-at ISO] [--no-pixels]`** is the server's
side, in place of `finder_ingest`. It sends the night in chunks, then runs the pixel checks:

- **`POST /finder/ingest`**, one chunk per request, at most `PH_INGEST_MAX_BYTES` (8 MB; 413
  above it; `Content-Length` required). Body: `{run_id, run_started_at?, candidates: [{id:
  "<tic>_<n>", candidate: {...}}], monitor: [star records], summary?, sensitivity?, final}`.
  Candidates are upserted exactly as `finder_ingest` step 1 does (their `vetting` block
  included), and dismissed from their own `known_lists` (step 2a). The summary and sensitivity
  are stored (step 3). Monitor records are stored under `run_id`, which stays `running` until the
  chunk with `final: true` marks it done and prunes old runs (step 4). Answer: `{run_id,
  candidates: {created, updated, unchanged}, invalid: [{file, error}], dismissed, summary_stored,
  sensitivity_stored, monitor_stars, final, pruned_runs?}`. Invalid items are listed; the rest are
  stored. Not done over HTTP: the network re-check against the known lists (step 2b; HUNT
  already checks against the day's snapshot) and the pixel check (step 5, below).
- **`GET /finder/pixel-queue?limit=20&max_attempts=3`**: `{items: [{id, ephemeris_key,
  candidate}]}`, the same selection as step 5 (open, with a period, no vet for the current
  ephemeris or a failed one with attempts left; never-vetted first, then by score).
- **`POST /finder/candidates/{id}/pixel-vet`** `{ephemeris_key, vet}` or `{ephemeris_key,
  error}`: stores the server's `vet_pixels` result (checked like step 5's) or its failure (which
  counts toward `max_attempts`). 409 when the candidate's ephemeris changed meanwhile, 404 for an
  unknown id, 422 for both or neither of `vet` / `error` or an unknown verdict.
- **`POST /monitor/heartbeat`** `{state: "searching"|"vetting"|"ingesting"|"idle", runner_id?,
  run_id?, next_run_at?, queues?: {name: {done, listed?, running?}}}`, every few minutes. The
  latest one is kept. While `state` isn't `idle`, it keeps `run_id` live on the monitor. It feeds
  `GET /monitor/now`'s `runner`: `{state, run_id, next_run_at, last_seen_at, responding}`
  (`responding` is false after `PH_RUNNER_STALE_S` of silence; `null` if it never beat), and
  `GET /monitor/coverage/queues`: `{updated_at, queues}`, the ledger's counts per queue.
- **`label`** on `POST /monitor/progress` (`fast`, `deep`, `faint`: lower-case slug, ≤ 20): stored
  in the star's record as `label`; `GET /monitor/now` repeats it at the top level.

## Configuration (env)

| Variable | Default | What it sets |
|---|---|---|
| `PH_DATABASE_URL` | none | Postgres URL; when set, used instead of SQLite |
| `PH_DB_PATH` | `spotter.db` | SQLite file (when `PH_DATABASE_URL` is unset) |
| `PH_DB_POOL_MAX` / `PH_DB_TIMEOUT_S` / `PH_DB_STATEMENT_TIMEOUT_MS` | `5` / `5` / `15000` | Postgres pool |
| `PH_ADAPTERS` | `fake` | `real`: `finder_ingest` uses pixels/ and hunter's known lists |
| `PH_WEB_ORIGIN` | none | CORS: the web app's origin (comma-separated for several) |
| `PH_TRUSTED_PROXY_HOPS` | `0` | proxies appending to X-Forwarded-For (Render: `1`); `0` uses the socket address |
| `PH_RATE_READ_PER_MIN` | `120` | GET requests per IP per minute |
| `PH_RATE_VOTE_PER_MIN` | `20` | votes per IP per minute |
| `PH_RATE_ADMIN_PER_MIN` | `6` | export requests per IP per minute |
| `PH_FINDER_VOTES_NEEDED` | `5` | `needs_votes=true`: open candidates with fewer votes than this |
| `PH_ADMIN_TOKEN` | none | enables `POST /finder/export/ctoi` (404 while unset) |
| `PH_INGEST_TOKEN` | none | enables the search server's routes (progress, heartbeat, ingest, pixel queue; 404 while unset) |
| `PH_RATE_INGEST_PER_MIN` | `600` | progress posts per IP per minute |
| `PH_MONITOR_LIVE_TIMEOUT_S` | `900` | a running sweep silent this long is no longer "live" |
| `PH_MONITOR_STEP_S` | `20` | replay: seconds per star |
| `PH_MONITOR_KEEP_RUNS` | `3` | finished runs whose stars (with light curves) are kept |
| `PH_RUNNER_STALE_S` | `900` | the search server is "not responding" after this long without a heartbeat |
| `PH_INGEST_MAX_BYTES` | `8000000` | largest `POST /finder/ingest` chunk |

## Storage

The two backends have the same tables and keys:
- **SQLite** (dev, tests) applies `src/api/storage/migrations/sqlite/*.sql`.
- **Postgres** (prod, e.g. Supabase through its connection pooler) applies
  `src/api/storage/migrations/*.sql`, in order and under an advisory lock.

Migrations run on startup of the API and of `finder_ingest`. `python -m api.migrate` (or `--database-url URL`) applies them on their own and
exits; run it before a deploy (docs/DEPLOY.md). To change the schema, add the next
numbered file to both folders; never edit one that has been applied.

| Migration | Tables |
|---|---|
| `0001_init` (Postgres only) | traps, discoveries, catches, jobs (dropped by 0006) |
| `0002_events` | `events`: `id` PK, `type`, `category`, `frame`, `observed_at`, `ra/dec` (nullable), `confidence`, `has_images`, `from_latest_observed_window`, `record` jsonb, plus content hashes. It also creates `event_sources`, `ingest_status` and `ph_sep_deg()` (all dropped by 0006) |
| `0003_analyze` | `star_analyses` (one row per TIC: `data_marker`, `analyzed_at`, `marker_checked_at`, `result`), `star_names`, `analyze_jobs` (dropped by 0006) |
| `0004_stardata` | `star_lightcurves` (one row per TIC: `status` `stored`/`no_data`, `data_marker`, `stored_at`, `curve`), `known_planets` (one row per TIC: `host_name`, `star`, `planets`, `fetched_at`). Dropped by 0006 |
| `0005_finder` | `candidates` (`id` "<tic>_<n>", `record` jsonb, `score`, `status` `new`/`under review`/`dismissed`/`exported`, `status_reason`, plus copies for filters: radius, period, pixel verdict, vote tallies), `pixel_vets` (latest vet per candidate and the ephemeris it ran on), `votes` (PK candidate + hashed voter key), `sensitivity` and `finder_sweep` (one row each) |
| `0006_finder_only` | Drops every table of 0001–0004 and `ph_sep_deg()` (v2 is the finder only). Adds `candidates.vetting` (VET's block) and the monitor: `monitor_runs` (`run_id` PK, `state` `running`/`done`, `started_at`, `finished_at`, `updated_at`), `monitor_shards` (progress per shard), `monitor_stars` (every star of the kept runs, full `record`), `monitor_seen` (each star's latest search: outcome, counts, 5° cell), `monitor_sectors`, `monitor_reasons` |
| `0007_monitor_detail` | `monitor_seen.known_count` / `rejected_count` (backfilled) and an index on `monitor_stars (tic, searched_at DESC)` |
| `0008_runner` | `monitor_heartbeat`: the search server's latest heartbeat (one row) |

`uv run pytest` runs every storage-touching test on both backends. Postgres comes from
`PH_TEST_DATABASE_URL`, a throwaway database that the tests wipe. If that's unset, it comes from a
disposable `postgres:16` Docker container. `PH_TEST_BACKENDS=sqlite` (or `postgres`) runs just
one backend.

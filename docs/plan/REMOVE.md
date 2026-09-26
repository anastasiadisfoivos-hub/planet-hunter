# REMOVE: what goes, what stays

Planet Hunter becomes one product: an open-source planet finder with a public monitor.
Events, the sky map and the lab are removed. The old site is preserved at tag
`v1-spotter` (= `08c9b75`, branch `polish`), so nothing below is lost; it is only left out.

## How the repository looks today (inventory, 2026-09-26)

`origin/main` is a single empty commit (`93cf5fa init`). The product lives on feature branches
that were never merged into `main`:

| Branch | Top-level paths | What it is |
|---|---|---|
| `polish` (= tag `v1-spotter`) | `web/` | the Next.js site: home, /events, /sky, /lab, /finder |
| `finderapi` | `api/ contracts/ events/ images/ pipeline/ pixels/ sources/` | FastAPI back end incl. finder routes, merged with stardata/spotapi/pixels |
| `deephunt` | `hunt/ pipeline/` | the newest search code (stitching, long BLS, TLS, single/duo dips) |
| `hunt` | `hunt/ pipeline/` | older search + committed `sensitivity.json` and sweep summaries |
| `pixels` | `pixels/ pipeline/` | difference-image vetting (`skypixels`) |
| `pipeline` | `pipeline/` | `hunter`: one-star transit + flare search (the base `hunt/` builds on) |
| `deploy` | `.github/ deploy/ README.md` | CI, nightly spotter checker, API image, Dockerfile, hosting notes |
| `stardata`, `api`, `spotapi`, `storage`, `traps` | `api/ contracts/ …` | earlier API states, all contained in or superseded by `finderapi` |
| `events`, `pictures`, `rubin`, `spectra`, `forecast`, `skymap`, `mapui`, `homepage` | one package each | spotter features |

So "removing" is mostly **not bringing things into `main`**. The build order in
[ROADMAP.md](ROADMAP.md) Phase 0 assembles `main` from the paths marked KEEP below.

## 1. Whole packages / directories

| Path | Source branch | Decision | Why |
|---|---|---|---|
| `hunt/` | `deephunt` | **KEEP** (the core) | the nightly search; newest code is on `deephunt` (+ `hunt/results/` from `hunt`) |
| `pipeline/` (`hunter`) | `deephunt` | **KEEP** | `hunt/` depends on it by path (fetch, BLS, measure, known-list matching) |
| `pixels/` (`skypixels`) | `pixels` | **KEEP** | difference-image vetting; the #1 false-positive check |
| `api/` | `finderapi` | **KEEP, trimmed** (§2) | finder routes, ingest, storage, CTOI export |
| `web/` | `polish` | **KEEP, trimmed** (§3) | finder pages + shell + UI kit |
| `contracts/` | `finderapi` | **REPLACE** | schemas are spotter shapes (`Discovery`, `Forecast`, `Sphere`, `StarTarget`, `heatmap`); write a new `contracts/` for Candidate, SearchLog, MonitorFrame (see [PRODUCT.md](PRODUCT.md)) |
| `events/` (`skyevents`) | `finderapi`/`events` | **DELETE** | live sky-event feed from 10 sources |
| `images/` (`skypictures`) | `finderapi`/`pictures` | **DELETE** | event pictures. The finder only used `starPic()` for a decorative star photo; replace with a runtime HiPS2FITS/DSS cutout URL or drop it |
| `sources/` (`skysources`) | `finderapi`/`rubin` | **DELETE** | Rubin alert brokers, SkyBoT, heatmap |
| `forecast/` (`skyforecast`) | `forecast` | **DELETE** | trap forecasts |
| `spectra/` | `spectra` | **DELETE** | lab chemical fingerprints |
| `deploy/` | `deploy` | **KEEP, rewrite** | Dockerfile must stop installing skyevents/skypictures/skysources; HOSTING/SETUP rewritten for the finder |

## 2. `api/` (from `finderapi`)

### Routes

| Route | File | Decision |
|---|---|---|
| `GET /finder/candidates`, `GET /finder/candidates/{id}` | `routes/finder.py` | KEEP (rename prefix later if the site drops `/finder`) |
| `GET /finder/funnel`, `GET /finder/sensitivity` | `routes/finder.py` | KEEP |
| `POST /finder/candidates/{id}/vote` | `routes/finder.py` | KEEP for now; see PRODUCT.md "Community review" (votes are advisory, never a vetting stage) |
| `POST /finder/export/ctoi` | `routes/admin.py` | KEEP (admin-only) |
| `GET /healthz` | `app.py` | KEEP |
| `GET /events`, `GET /events/{id}` | `routes/events.py` | DELETE |
| `GET /status` (sources/Rubin status) | `routes/events.py` | DELETE; replaced by `GET /monitor/status` (new) |
| `POST /analyze`, `GET /jobs/{id}`, `GET /stars/{tic}/analysis` | `routes/analyze.py` | DELETE. On-demand "analyze any star" is a different product, costs an always-on worker, and would show unvetted "signals" next to vetted candidates |
| `GET /stars/{tic}/lab` | `routes/stars.py` | DELETE |
| `GET /stars/{tic}/lightcurve` | `routes/stars.py` | KEEP the idea, move to `/stars/{tic}` in a new `routes/stars.py` fed by the nightly search's per-star record (search log + light curve), not by `/analyze` |
| new: `/monitor/*`, `/search-log`, `/coverage` | — | ADD (PRODUCT.md) |

### Modules

| Module | Decision |
|---|---|
| `finder.py`, `finder_ingest.py`, `finder_export.py`, `honesty.py`, `ratelimit.py`, `settings.py`, `deps.py`, `timeutil.py`, `models.py` (finder parts), `ports.py` (KnownLists, PixelVetter, Storage) | KEEP |
| `storage/finder_sql.py`, `storage/postgres.py`, `storage/sqlite.py`, finder migrations | KEEP |
| `adapters/finder_real.py` (PixelsVetter, HunterKnownLists), `adapters/exoarchive.py` (known planets on a star, for the dossier) | KEEP |
| `fakes/finder.py`, `fakes/archive.py` | KEEP (tests) |
| `lightcurve.py` | KEEP (binning for served curves) |
| `ingest.py`, `storage/events_sql.py`, `routes/events.py` + events migrations | DELETE |
| `analysis.py`, `jobs.py`, `precompute.py`, `adapters/real.py` (PipelineAnalyzer), `fakes/tess.py`, `routes/analyze.py` | DELETE |
| `lab.py`, `spectra_index.py`, `known_systems.py`, `routes/stars.py` (lab) | DELETE |
| `pyproject.toml` deps `skyevents`, `skypictures`, `skysources` | DELETE; keep `hunter`; `skypixels` stays the `finder` extra |
| tests: `test_events.py`, `test_ingest.py`, `test_analyze.py`, `test_lab.py`, `test_precompute.py`, `sample_events.py` | DELETE; keep `test_finder*.py`, `test_storage.py` (finder parts), `test_ratelimit.py`, `test_fold.py` |
| DB tables for events, analyses, star_lightcurves (from `/analyze`), jobs, star_names, known_planets cache (keep this one) | DROP in a migration (hosted DB) |

**Stardata parts the finder uses**: the `exoarchive` adapter and `known_planets` cache (dossier shows
known planets on the star), `lightcurve.py` binning, TIC 8.2 star parameters. Everything else in
stardata (lab view, spectra index, per-star Lab) goes.

### ExoFOP wording to keep (verified)
`finder_export.py` and `api/README.md` say ExoFOP "require[s] the URL of a published, refereed
paper for every new CTOI". That is **correct** since ExoFOP's 2026-08-19 news item (quotes in
[SCIENCE.md §8](SCIENCE.md#8-submit-exofop-ctoi)). Keep it, add the news.php link and date, and
add the "approval to upload candidates is required" step to the export docs.

## 3. `web/` (from `polish` / `v1-spotter`)

### Routes

| Route | Decision |
|---|---|
| `/` (`app/page.tsx`: hero sky, this week, three doors) | REPLACE with the monitor home (PRODUCT.md) |
| `/events`, `/events/[id]` | DELETE |
| `/sky` | DELETE |
| `/lab`, `/lab/thermometer`, `/lab/hear-a-star`, `/lab/hubble`, `/lab/fingerprints`, `/lab/star/[tic]` | DELETE |
| `/finder`, `/finder/[id]`, `/finder/sensitivity` | KEEP → become `/candidates`, `/candidates/[id]`, `/sensitivity` (redirect old paths) |
| `/credits` | KEEP, trim to data/tool credits |
| new: `/methods`, `/search-log`, `/coverage`, `/stars/[tic]`, `/about` | ADD |

### Components and libraries

| Path | Decision |
|---|---|
| `components/finder/*` | KEEP |
| `components/ui/*`, `components/shell/*`, `app/tokens.css`, `app/globals.css`, `app/layout.tsx` | KEEP; `shell/nav.ts` NAV becomes Monitor / Candidates / Search log / Sensitivity / Methods; `StarSearch` switches from map hosts to "stars we searched" |
| `components/lab/chart.tsx`, `components/lab/hooks.ts`, `components/lab/lab.module.css` | MOVE to `components/charts/` first — `finder/LightCurves.tsx`, `Funnel.tsx`, `Sensitivity.tsx`, `CandidateList.tsx`, `Report.tsx` import `linear`, `ticks`, `nf0`, `LoadError`, `useWidth` and `lab.module.css` from there — then delete the rest of `components/lab/` |
| `components/picture/Drawer.tsx`, `Info.tsx`, `Sparkline.tsx` | KEEP (used by finder); `Picture.tsx`, `FadeImage.tsx`, `TypoTile.tsx` keep only if the star thumbnail stays |
| `components/map/**` (incl. `scene/`), `components/gallery/**`, `components/events/**`, `components/home/ThisWeek.tsx` | DELETE |
| `components/home/Candidates.tsx` | KEEP → monitor home "latest candidates" strip |
| `lib/api.ts` | KEEP finder part (types `Candidate*`, `PixelVet`, `Votes`, `Sensitivity`, `FunnelStep`; `getCandidates`, `getCandidate`, `submitVote`, `getSensitivity`, `exportCtoiCsv`); DELETE events/analyze/lab part (`getEvents`, `getEvent`, `getStatus`, `analyze`, `getJob`, `getStarLab`, `getStarLightcurve`, `STEPS`, `clockNow`, `getAllEvents`); `getMapHostTics` goes with the map |
| `lib/format.ts` | KEEP |
| `lib/pictures.ts`, `lib/pictureKeys.ts` | KEEP only `starPic` if thumbnails stay; drop `eventPic`, `wherePic` |
| `lib/contract.ts`, `lib/events.ts`, `lib/eventStyle.ts`, `lib/markers.ts`, `lib/sky.ts`, `lib/skyTexture.ts`, `lib/galactic.ts`, `lib/sun.ts`, `lib/starColor.ts`, `lib/starColorTable.ts`, `lib/hosts.ts`, `lib/images.ts` | DELETE (only map, gallery and lab import them) |
| `lib/data.ts` | DELETE after moving the `HostsFile`-style type that `shell/StarSearch.tsx` and `lib/api.ts` import from it (checked: those are its only non-map importers) |
| `state/store.tsx` | DELETE (checked: imported only by `components/map/*` and `components/gallery/Gallery.tsx`) |
| `tests/finder/finder.test.ts`, `tests/shell.test.ts` | KEEP; all other `tests/*` (map, sky, events, lab, flight, rig, galactic, markers, starColor, skyTexture, images, analyze) DELETE |

### Data and images

| Path | Size | Decision |
|---|---|---|
| `public/data/finder/*` (mock index, folds, sensitivity, 14 candidate mocks) | small | KEEP until the API is live, then delete mocks |
| `public/data/events.mock.json`, `heatmap.rubin-sample.json`, `rubin-footprint.json`, `sky-objects.json`, `bright-stars.json`, `land-110m.json`, `hosts.json`, `status.mock.json`, `sky/*` (d3-celestial), `lab/*`, `analysis/wasp-18` | ~2.5 MB total with finder | DELETE |
| `public/images/events/` (47), `sky/` (54), `feature/` (5) | ~18 MB | DELETE |
| `public/images/stars/` (17) | 1.6 MB | DELETE unless thumbnails stay |
| `public/images/credits.json` | | TRIM |
| `scripts/build-*.mjs` (bright-stars, events-mock, hosts, land, picture-marks, sky-objects, sky, star-colors), `scripts/rubin_footprint.py` | | DELETE; keep `build-finder-folds.mjs` |
| `docs/mapui`, `docs/spotmap`, `docs/lab`, `docs/graphics-pass`, `docs/polish` (mocks, refs, extracted sites) | ~200 images | DELETE from the new tree (they live on at `v1-spotter`); keep `docs/finder` |
| `DESIGN.md` | | KEEP as a starting point; its "image-led, events gallery" rules are rewritten in the design phase |

## 4. Workflows (`.github/workflows/` and `*/ci/*.yml`)

| Workflow | Where | Decision |
|---|---|---|
| `ci.yml` | `deploy` | KEEP; package list becomes `api pipeline hunt pixels` (drop `sources forecast`) |
| `nightly.yml` (api.nightly traps checker + Rubin heatmap to `heatmap-data` branch) | `deploy` | DELETE |
| `image.yml` (API image pre-warmed with WASP-18/121/43, TOI-700 for `/analyze`, Render deploy hook) | `deploy` | REWRITE: API image without the TESS pre-warm (no `/analyze`); keep the Render hook |
| `hunt/ci/sweep.yml` → `.github/workflows/sweep.yml` | `deephunt` | KEEP (the nightly search); change per [ROADMAP.md](ROADMAP.md) Phase 2 |
| `api/ci/finder.yml` → `finder-ingest.yml` | `finderapi` | KEEP |
| `api/ci/ingest.yml` (hourly events) and `events/ci/ingest.yml` | `finderapi` | DELETE |
| `api/ci/precompute.yml` (weekly `/analyze` pre-compute of 1,748 map hosts) | `finderapi` | DELETE |
| repo variables/secrets `PH_NIGHTLY_ENABLED`, `PH_HEATMAP_ENABLED`, `PH_PREWARM_STARS` | GitHub settings | DELETE; keep `PH_DATABASE_URL`, `PH_ADMIN_TOKEN`, `RENDER_DEPLOY_HOOK_URL` |
| branch `heatmap-data` | GitHub | not on the remote today (checked `git ls-remote`); make sure `nightly.yml` never creates it |

## 5. Branches after `main` is assembled

Retire (delete on the remote once `main` builds; the tag keeps the site):
`events pictures rubin spectra forecast skymap mapui homepage polish traps storage spotapi api stardata`.
Retire after their code is on `main`: `pipeline hunt deephunt pixels finderapi deploy`.
Keep: tag `v1-spotter`.

## 6. Hosted things

| Thing | Decision |
|---|---|
| Postgres tables for events, analyses, jobs, star names, lab light curves | drop (migration) |
| finder tables (candidates, votes, pixel vets, funnel, sensitivity) | keep; add search-log tables (PRODUCT.md) |
| GHCR image `planet-hunter-api` with TESS pre-warm | rebuild without pre-warm |
| Vercel/Render projects | keep; point at the new `main` |

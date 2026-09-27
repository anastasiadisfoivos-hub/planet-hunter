# Local end-to-end run (27 Sep 2026)

The release branch, run on one laptop the way it will run live, with real data only.

1. **Database:** Postgres 16 in Docker; `python -m api.migrate` applied 0001–0008.
2. **API:** `uvicorn --factory api.app:create_app` on that database, with `PH_INGEST_TOKEN`, `PH_ADMIN_TOKEN`
   and `PH_WEB_ORIGIN=http://localhost:3100`.
3. **Ingest:** the real 2026-09-26 sweep of 200 stars (hunt's `results/<tic>.json` and its summary), turned into
   monitor records with `runner/scheduler/monitor_record.py`, sent over HTTP with `python -m api.remote_ingest`
   (the path the Oracle server uses; no database URL on the sending side), plus `hunt/results/sensitivity.json`.
   The API then held 200 stars, 427 signals (130 already known, 297 rejected) and 0 candidates.
4. **Web:** `next build` with `NEXT_PUBLIC_API_BASE=http://localhost:8100`, served on :3100; screenshots taken
   with headless Chromium. No console errors.

| File | Page | Data |
|---|---|---|
| `monitor.png` | `/` | replay of the 26 Sep search from the API; TIC 201604954 with its real TESS curve |
| `monitor-no-curve.png` | `/` | a star the sweep stored no curve for (186 of the 200: hunt's result files hold no curve; the runner's records do) |
| `candidates.png` | `/candidates` | the sweep's funnel; the list is empty and says so |
| `log.png` | `/log` | all 200 stars, the sky coverage |
| `methods.png` | `/methods` | the Methods text |
| `sensitivity.png` | `/sensitivity` | hunt's injection-recovery run, as stored by the API |
| `credits.png` | `/credits` | picture credits |
| `dossier-standin-mock*.png` | `/candidates/tic415739607-01` | **mock mode** (no API): the real sweep has no candidate, so no real dossier exists yet. This is TOI-7303.01, a known TOI, shown as a labelled stand-in |

`docs/screenshots/` (used by the top-level README) holds copies of `monitor`, `candidates`, `sensitivity` and the
stand-in dossier; they are retaken from the deployed site after go-live.

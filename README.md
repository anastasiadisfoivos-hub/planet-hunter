# planet-hunter

A public website where visitors **watch** stars and patches of sky. When real telescope data turns
up something in a watched spot, the visitor sees the detection. The data comes from:

- **NASA TESS**: light curves of individual stars, searched for transit-like dips and flares.
- **Rubin Observatory (LSST)**: public alert-broker streams for a patch of sky: supernovae,
  asteroids, variable stars, and more.

There are no accounts and no points. A visitor is a random ID kept in their browser.

## Honesty rule

The site reports **detections and candidates, never discoveries**. No code, UI text, API response
or doc may say **"discovered"** or **"new planet"**. Every type is a best guess with a confidence
(0–1), and every detection says whether it's already on a known list (`known`, `not_on_lists`,
`unchecked`). The API enforces this with `api/src/api/honesty.py` and its tests.

## Folder map

| Folder | What it is | Stack |
|---|---|---|
| [`pipeline/`](pipeline/) | TESS science: hunt one star for transits and flares (package `hunter`) | Python 3.12, uv, lightkurve, astropy |
| [`sources/`](sources/) | Rubin broker clients, visit schedule, SkyBoT / known solar-system objects, whole-sky heatmap (package `skysources`) | Python 3.12, uv, httpx, astropy |
| [`forecast/`](forecast/) | Forecast engine: what a sky patch is likely to catch, and when (package `skyforecast`) | Python 3.12, uv, numpy, scipy |
| [`api/`](api/) | FastAPI backend: traps, hunts, forecasts, detections. Uses fakes until the siblings are wired in | Python 3.12, uv, FastAPI |
| [`web/`](web/) | Front end: sky map and star picker | Next.js, TypeScript |
| [`contracts/`](contracts/) | The shared data shapes (`CONTRACT.md`, `CONVENTIONS.md`, JSON Schemas) | – |
| [`deploy/`](deploy/) | Dockerfile, hosting research ([`HOSTING.md`](deploy/HOSTING.md)), go-live steps ([`SETUP.md`](deploy/SETUP.md)) | Docker |
| [`.github/workflows/`](.github/workflows/) | CI (`ci.yml`), nightly checker + heatmap (`nightly.yml`), pre-warmed API image (`image.yml`) | GitHub Actions |

Each Python folder is its own uv project with its own `pyproject.toml` and `uv.lock`.

## Running it locally

You need [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you) and Node.js 22+.

### api/ (backend, with fake data)

```sh
cd api
uv sync
uv run pytest -q                                   # tests (fakes, in-memory SQLite)
uv run uvicorn --factory api.app:create_app        # http://localhost:8000, docs at /docs
uv run python -m api.nightly --dry-run             # the nightly checker, writing nothing
```

Every request needs an `X-Player-Id: <uuid>` header. Configuration is through `PH_*` environment
variables, listed in [api/README.md](api/README.md).

### pipeline/ (TESS)

```sh
cd pipeline
uv sync
uv run pytest -q                                   # offline tests (network tests are skipped)
uv run pytest -q --run-network                     # also the ones that download real TESS data
uv run python -m hunter WASP-18 --out out/         # hunt one star; writes result.json + plots
```

### sources/ (Rubin + solar system + heatmap)

```sh
cd sources
uv sync
uv run pytest -q                                   # offline, replays recorded responses
uv run python -m skysources.heatmap --nights 3 --until latest --out heatmap.json
```

### forecast/

```sh
cd forecast
uv sync
uv run pytest -q
uv run python examples/worked_examples.py          # three worked examples on fake providers
```

### web/

```sh
cd web
npm install
npm run dev                                        # http://localhost:3000, mock data by default
npm run lint && npm run build
```

To point the site at a local API instead of mock data:

```sh
NEXT_PUBLIC_API_MOCK=false NEXT_PUBLIC_API_BASE=http://localhost:8000 npm run dev
```

Then start the API with `PH_CORS_ORIGINS=http://localhost:3000` so the browser may call it.

### Everything in Docker (the image that gets deployed)

From the repo root:

```sh
docker build -f deploy/Dockerfile -t planet-hunter-api .
docker run --rm -p 8000:8000 planet-hunter-api               # fakes on
docker run --rm -p 8000:8000 -e PH_ADAPTERS=real planet-hunter-api   # once the adapters are wired
docker build -f deploy/Dockerfile --build-arg PREWARM_STARS="WASP-18,WASP-121" -t planet-hunter-api .   # bake in TESS data (needs network)
```

The image contains `api/` plus whichever of `pipeline/`, `sources/` and `forecast/` exist.

## CI and scheduled jobs

- **`ci.yml`** runs on every push and PR:
  - `uv run pytest -q -m "not network"` for each Python package present;
  - `npm ci && npm run lint && npm run build` for `web/`;
  - a Docker build plus a `/healthz` smoke test.
- **`nightly.yml`** runs daily at 09:17 UTC:
  - `python -m api.nightly`;
  - the heatmap build, published to the `heatmap-data` branch.

  Each job is off until its repo variable (`PH_NIGHTLY_ENABLED`, `PH_HEATMAP_ENABLED`) is `true`.
  Either can be started by hand from the Actions tab.
- **`image.yml`** runs nightly and on every push to `main`, once `PH_IMAGE_ENABLED` is `true`:
  - builds the API image with the TESS cache pre-warmed for the "Known systems" stars
    (WASP-18, WASP-121, WASP-43, TOI-700);
  - pushes it to `ghcr.io`;
  - redeploys Render.

## Hosting

All free tier, no credit card anywhere:

- API: Render
- Database and accounts: Supabase (Postgres + Auth)
- Front end: Vercel Hobby
- Scheduled jobs: GitHub Actions

Why these, and what each free tier can't do, is in [deploy/HOSTING.md](deploy/HOSTING.md).
The go-live checklist is [deploy/SETUP.md](deploy/SETUP.md).

# Going live: step by step

Everything here is **FREE** and asks for **no credit card**. If any screen asks for card or
payment details, **stop**. That means something changed; don't enter one.
Why these hosts: [HOSTING.md](HOSTING.md).

Where things run:

```
browser ──> Vercel Hobby (web/, static Next.js)
               │  NEXT_PUBLIC_API_BASE
               ▼
            Render Free (deploy/Dockerfile: api/ + pipeline/ sources/ forecast/)
               │  PH_DATABASE_URL
               ▼
            Neon Free (Postgres)  <── GitHub Actions nightly.yml: api.nightly (daily)
GitHub Actions nightly.yml: heatmap build ──> branch heatmap-data/heatmap.json ──> web/
```

Names used below (change them if you like, but keep them consistent):
- GitHub repo `anastasiadisfoivos-hub/planet-hunter`
- Render service `planet-hunter-api`, so the API URL is `https://planet-hunter-api.onrender.com`
- Vercel project `planet-hunter`, so the site URL is `https://planet-hunter.vercel.app`
- Neon project `planet-hunter`

Steps marked **(Claude can do)** can be done from the terminal once you have logged in to that
CLI yourself. Tokens never go into the repo or the chat.

---

## 0. Before Sunday: code that must be on `main` (FREE)

1. Merge into `main` the branches that are ready: `traps` (api/ + contracts/) first, then
   `deploy`, then `pipeline`, `rubin` (sources/), `forecast`, `skymap` (web/). Use PRs, so
   `ci.yml` checks each one.
   - Render and Vercel deploy from `main`, so nothing can go live until `api/` is there.
2. **Blocker for keeping data:** api/ stores everything in SQLite, and Render Free wipes its disk
   every time the service sleeps (after 15 min without traffic).
   - The TRAPS session (api/ owner) needs to add a Postgres `Storage` that reads
     `PH_DATABASE_URL`, used whenever that variable is set.
   - Without it the site still works, but traps and catches reset whenever the API sleeps.
     Launch it labelled as a demo, or wait.
3. For real data rather than fakes, `api/src/api/adapters/real.py` must be wired to the siblings
   (TRAPS session). Until then keep `PH_ADAPTERS=fake`.

## 1. Neon: the database (FREE, no card) (Claude can do, after `npx neonctl auth`)

1. Go to https://neon.com → **Sign up** → **Continue with GitHub**. The Free plan is the default;
   don't pick a paid plan.
2. **Create project**:
   - Name `planet-hunter`
   - Postgres 17
   - Region **AWS Europe Central 1 (Frankfurt)**, the same region as Render in step 2
3. On the project dashboard → **Connect** → enable **Connection pooling** → copy the connection
   string. It looks like `postgresql://…@ep-…-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require`.
4. Keep it somewhere private (a password manager). It goes into Render (step 2) and GitHub (step 4).

## 2. Render: the API (FREE, no card)

1. Go to https://dashboard.render.com → **Sign up with GitHub**. When asked about billing, skip or
   close it. Don't add a card.
2. **New +** → **Web Service** → **Build and deploy from a Git repository** → connect GitHub →
   choose `anastasiadisfoivos-hub/planet-hunter`.
3. Fill in:
   - Name: `planet-hunter-api`
   - Region: **Frankfurt (EU Central)**
   - Branch: `main`
   - Root Directory: *(leave empty)*
   - Language / Runtime: **Docker**
   - Instance Type: **Free**
4. **Advanced**:
   - Dockerfile Path: `./deploy/Dockerfile`
   - Docker Build Context Directory: `.`
   - Health Check Path: `/healthz`
   - Auto-Deploy: **On Commit**
5. **Environment Variables** (Add Environment Variable):

   | Key | Value |
   |---|---|
   | `PH_ADAPTERS` | `fake` (change to `real` once the adapters are wired) |
   | `PH_CORS_ORIGINS` | `https://planet-hunter.vercel.app` (the exact Vercel URL from step 3; comma-separate several) |
   | `PH_MAX_CONCURRENT_HUNTS` | `1` (512 MB RAM: one hunt at a time) |
   | `PH_HUNT_TIMEOUT_S` | `600` (0.1 CPU: a 2-sector hunt takes ~3 min) |
   | `PH_SWEEP_TIMEOUT_S` | `30` |
   | `PH_DATABASE_URL` | the Neon string from step 1. Only has an effect once api/ has Postgres storage (step 0.2) |

   Don't set `PORT`: Render sets it, and the image listens on `$PORT`.
6. **Deploy Web Service**. The first build takes ~5–10 min.
7. Check: `curl https://planet-hunter-api.onrender.com/healthz` should give `{"ok":true}`.
   - The first request after a sleep takes ~1 min.
   - API docs: `https://planet-hunter-api.onrender.com/docs`.

## 3. Vercel: the web site (FREE, no card) (Claude can do, after `npx vercel login`)

1. Go to https://vercel.com/signup → **Hobby** → **Continue with GitHub**.
2. **Add New…** → **Project** → import `anastasiadisfoivos-hub/planet-hunter`.
3. Configure:
   - Project Name: `planet-hunter`
   - Framework Preset: **Next.js**
   - Root Directory: **`web`** (click Edit and pick the folder)
4. **Environment Variables** (all environments):

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_MOCK` | `false` |
   | `NEXT_PUBLIC_API_BASE` | `https://planet-hunter-api.onrender.com` |

   These are baked in at build time, so after changing them, redeploy (Deployments → ⋯ → Redeploy).
5. **Deploy**. Note the production URL. If it isn't `https://planet-hunter.vercel.app`, go back to
   Render → `planet-hunter-api` → Environment and set `PH_CORS_ORIGINS` to the real URL.
6. Hobby is for non-commercial use: no ads, no paid features.

## 4. GitHub: secrets and switches for the nightly jobs (FREE) (Claude can do with `gh`)

The repo is public, so Actions minutes are free.

1. Repo → **Settings** → **Secrets and variables** → **Actions**.
2. **Secrets** tab → **New repository secret**:
   - `PH_DATABASE_URL` = the Neon string from step 1
3. **Variables** tab → **New repository variable**:

   | Name | Value | When |
   |---|---|---|
   | `PH_HEATMAP_ENABLED` | `true` | As soon as `sources/` is on `main`. It needs no secret. |
   | `PH_NIGHTLY_ENABLED` | `true` | Only after api/ has Postgres storage (step 0.2). Before that, the nightly checker would work on a throwaway database. |
   | `PH_ADAPTERS` | `real` | Once the real adapters are wired (step 0.3) |

   The same from the terminal:
   ```sh
   gh secret set PH_DATABASE_URL -R anastasiadisfoivos-hub/planet-hunter      # paste when prompted
   gh variable set PH_HEATMAP_ENABLED -b true -R anastasiadisfoivos-hub/planet-hunter
   ```
4. Test by hand: **Actions** → **nightly** → **Run workflow**.
   - "dry run" is ticked by default, so the checker only counts and writes nothing.
   - The heatmap job pushes `heatmap.json` to the `heatmap-data` branch, served at
     `https://raw.githubusercontent.com/anastasiadisfoivos-hub/planet-hunter/heatmap-data/heatmap.json`.
5. Scheduled runs are at 09:17 UTC daily. GitHub pauses schedules after 60 days with no commits.
   If that happens, click **Enable workflow** on the Actions tab.

## 5. Final checks (FREE)

1. `curl https://planet-hunter-api.onrender.com/healthz` gives `{"ok":true}`.
2. Open `https://planet-hunter.vercel.app`, place a sky watch, and see the sweep come back.
   - With `PH_ADAPTERS=fake`, the results are fake. The web app must show its demo tag.
3. Browser devtools → Network: requests to the API have no CORS errors. If they do, fix
   `PH_CORS_ORIGINS` (step 2.5).
4. Actions tab: the latest `ci` run on `main` is green.

## Still needed from other sessions (not deploy's area)

- **api/ (TRAPS):**
  - Postgres `Storage` using `PH_DATABASE_URL` (step 0.2);
  - real adapters (step 0.3).
- **web/ (SKYMAP):** read the heatmap from a URL setting, e.g.
  `NEXT_PUBLIC_HEATMAP_URL=https://raw.githubusercontent.com/anastasiadisfoivos-hub/planet-hunter/heatmap-data/heatmap.json`.
  raw.githubusercontent.com sends `Access-Control-Allow-Origin: *`.
  - While the API sleeps, show a "waking up (~1 min)" state instead of an error.
- **sources/ (RUBIN):** the README mentions a `skysources-heatmap` command, but `pyproject.toml`
  doesn't declare it yet. The workflow uses `python -m skysources.heatmap`, which works either way.

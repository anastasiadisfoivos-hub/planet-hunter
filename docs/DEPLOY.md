# Deploying planet-hunter (all free tiers)

Four places, each signed in with your GitHub account, plus the Oracle server:

| Piece | Where | Plan | Made from |
|---|---|---|---|
| Database (Postgres) | Supabase | Free | `api/src/api/storage/migrations/*.sql` |
| API (FastAPI) | Render | Free web service | `render.yaml`, `api/Dockerfile` |
| Website (Next.js) | Vercel | Hobby | `web/` |
| Nightly search | Oracle Cloud | Always Free (Ampere A1) | `runner/` |
| Tests | GitHub Actions | free on a public repo | `.github/workflows/ci.yml` |

**Part A** is what you (the owner) click, once. **Part B** is what SHIP runs after you say "go".
**Part C** is what each service costs (nothing, if the warnings there are followed).

Do Part A in order: each step needs a value from the step before.

---

## Part A: what you click (about 45 minutes)

### A0. Make three secrets and keep them in a password manager

On your Mac, in Terminal, run this three times and save each output with its name:

```sh
openssl rand -hex 32
```

(or: `python3 -c "import secrets; print(secrets.token_hex(32))"`)

| Name | What it is for |
|---|---|
| `PH_INGEST_TOKEN` | the Oracle server proves to the API that it is allowed to post the search's progress and results |
| `PH_ADMIN_TOKEN` | the ExoFOP export (`POST /finder/export/ctoi`). Optional: without it that endpoint is off (404) |
| Supabase database password | see A1 (you can also let Supabase generate it) |

Never paste these into GitHub, an issue, a chat, or a file in the repository.

### A1. Supabase (database)

1. Go to <https://supabase.com> → **Start your project** → **Continue with GitHub** → authorise.
2. If asked to create an organisation: any name, plan **Free**.
3. **New project**:
   - Name: `planet-hunter`.
   - Database password: click **Generate a password** (letters and digits only are easiest: no
     characters that need escaping in a URL). Save it.
   - Region: **Central EU (Frankfurt)** (the API on Render is in Frankfurt too).
   - Plan: **Free**.
   - If the form has a **Data API** / "Enable Data API" option (under security options), turn it
     **off**. The site never talks to Supabase directly; only our API does, over Postgres. With the
     Data API on, our tables in the `public` schema would also be reachable through Supabase's REST
     API. If the form has no such option, turn it off after creation: **Project Settings → Data
     API** (or **Integrations → Data API**) → **Enable Data API** off.
   - **Create new project**, wait ~2 minutes.
4. Get the connection string: click **Connect** (top of the project page) → **Connection string**
   → choose **Session pooler** (NOT "Direct connection", NOT "Transaction pooler").
   It looks like:
   ```
   postgresql://postgres.<project-ref>:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres
   ```
   Replace `[YOUR-PASSWORD]` with your password and add `?sslmode=require` at the end. This whole
   line is **`PH_DATABASE_URL`**. Save it in the password manager.

   Why the session pooler: the direct connection (`db.<ref>.supabase.co`) is IPv6-only on the free
   plan, and Render's free services connect over IPv4. The session pooler (port **5432**) works over
   IPv4 and keeps a normal Postgres session. (The transaction pooler on port 6543 would also work,
   since the API turns prepared statements off, but session mode is the simpler choice.)
5. Nothing else to do in Supabase: SHIP creates the tables (Part B).

### A2. Render (API)

1. Go to <https://render.com> → **Get Started** → **GitHub** → authorise.
2. If Render asks for a payment method: you can skip it for free services. **Do not add a card**
   (see Part C: with a card on file, going over a free limit is billed instead of paused).
3. Give Render access to the repository: **New +** → **Blueprint** → **Connect GitHub** → choose
   **Only select repositories** → `planet-hunter` → **Install**.
4. Back in **New Blueprint Instance**: pick the `planet-hunter` repository, branch **main**.
   Render reads `render.yaml` and shows one service, `planet-hunter-api`, plan **Free**. Check that it
   says **Free**. If it shows a price, stop and tell SHIP.
5. It asks for the values marked `sync: false`:
   | Key | Value |
   |---|---|
   | `PH_DATABASE_URL` | the Supabase session-pooler line from A1 (with `?sslmode=require`) |
   | `PH_INGEST_TOKEN` | from A0 |
   | `PH_ADMIN_TOKEN` | from A0 (or leave empty to keep the export off) |
   | `PH_WEB_ORIGIN` | leave for now; filled in A3 step 6 |
6. **Apply**. The first build takes a few minutes. When it is **Live**, copy the URL at the top of the
   service page, e.g. `https://planet-hunter-api.onrender.com`. That is the **API URL**. (If the
   name was taken, Render adds a suffix such as `-x1y2`: use the URL exactly as shown and tell SHIP.)
7. Check it: open `<API URL>/healthz` in the browser. It shows `{"ok":true}`. The first request after
   15 idle minutes takes about a minute (the free service sleeps; see Part C).

### A3. Vercel (website)

1. Go to <https://vercel.com/signup> → **Continue with GitHub** → plan **Hobby** → authorise.
2. **Add New… → Project** → **Import** the `planet-hunter` repository (grant access to it if asked:
   "Only select repositories").
3. On **Configure Project**:
   - **Root Directory**: click **Edit** → choose **`web`**. (Important: the repository root is not the
     website.)
   - **Framework Preset**: **Next.js** (detected automatically once the root is `web`).
   - Build / install / output settings: leave the defaults (`npm install`/`next build`).
   - **Environment Variables**: add
     | Name | Value | Environments |
     |---|---|---|
     | `NEXT_PUBLIC_API_BASE` | the API URL from A2, with no trailing `/` | **Production** only |

     Without `NEXT_PUBLIC_API_BASE` the site runs in demo (mock) mode with stand-in data. Setting it
     for Production only keeps preview deployments in demo mode, which is what we want: the API only
     accepts the production site's address (CORS).
4. **Deploy**. When it is done, copy the domain Vercel shows, e.g. `https://planet-hunter.vercel.app`.
   That is the **site URL**.
5. `NEXT_PUBLIC_*` values are built into the pages, so a change to one needs a new deployment:
   **Deployments → ⋯ → Redeploy**.
6. Back in Render: service **planet-hunter-api → Environment → `PH_WEB_ORIGIN`** = the site URL
   (`https://planet-hunter.vercel.app`, no trailing `/`) → **Save, rebuild and deploy**. Without it,
   the browser refuses the API's answers to the site (votes, the monitor).

### A4. Oracle Cloud (the nightly search server)

1. Sign up at <https://signup.cloud.oracle.com>. Oracle asks for a card **to verify your identity**;
   it does not charge it unless you upgrade the account (Part C). Choose your **home region**
   carefully (it cannot be changed; Always Free compute is only in the home region). Frankfurt is
   fine.
2. Stay on the **Free Tier** account. Do **not** click "Upgrade to Pay As You Go".
3. **Compute → Instances → Create instance**:
   - Image: **Canonical Ubuntu 24.04** (the aarch64/Arm image).
   - Shape: **Change shape → Ampere → VM.Standard.A1.Flex**. Look for the **Always Free-eligible**
     label.
     - **OCPUs and memory: see the warning.** Oracle's Always Free page (checked 27 Sep 2026) says
       A1 is free for the first **1,500 OCPU hours and 9,000 GB hours per month, "equivalent to
       2 OCPUs and 12 GB of memory"**. Older guides (and our roadmap) say 4 OCPUs / 24 GB. **Decided
       (27 Sep): 2 OCPUs, 12 GB**, the current free amount; the runner uses 2 workers (one per core).
       Anything above the free amount uses trial credit for 30 days and then is not free.
   - Networking: create a new VCN with a **public subnet**, **assign a public IPv4 address**.
   - SSH keys: **Generate a key pair for me** → **Save private key** (e.g. to
     `~/.ssh/oracle-planet-hunter.key`, then `chmod 600` it), or upload your own public key.
   - Boot volume: **Specify a custom boot volume size** → **200 GB**. The runner needs **at least
     200 GB** (it keeps its data under 150 GB, plus the system), and Always Free includes 200 GB of
     block storage in total, boot volumes included, so 200 GB is also the most that stays free.
     Don't create other volumes.
   - **Create**. Copy the **public IP address** when it is running.
4. Firewall: **Networking → Virtual cloud networks → your VCN → Security Lists → Default** →
   **Ingress rules**: the security list must allow **only TCP port 22** (SSH) inbound, from `0.0.0.0/0`. Delete any other ingress rule
   (e.g. ICMP is harmless but not needed). The server listens on nothing else.
5. Give SHIP: the public IP, the path of the private key on your Mac, and tell it the
   `PH_INGEST_TOKEN` is in your password manager (you type it yourself when `deploy.sh` asks).

### A5. GitHub

Nothing to set: `ci.yml` needs no secrets. The repository must stay **public** (Actions minutes
are free only for public repositories).

---

## Part B: commands SHIP runs after "go"

Placeholders: `$API` = the API URL, `$SITE` = the site URL. Secrets are typed at a prompt
(`read -s`), never put on a command line or in a file.

### B1. Merge `release` to `main`

```sh
git fetch origin
git switch main && git pull --ff-only
git merge --no-ff origin/release -m "Release: planet finder v2"
git push origin main
gh run watch "$(gh run list --branch main --workflow ci.yml --limit 1 --json databaseId -q '.[0].databaseId')"
```

`ci.yml` must be green: Render deploys `main` only after its checks pass
(`autoDeployTrigger: checksPass` in `render.yaml`).

### B2. Create the tables in Supabase

The API also applies pending migrations on every start (under a Postgres advisory lock, so two
starts at once are safe). Running them first, on their own, keeps a schema error out of the web
service's boot and shows what was applied:

```sh
cd api
read -rs PH_DATABASE_URL && export PH_DATABASE_URL     # paste the session-pooler URL
uv run python -m api.migrate
# -> postgres: applied 0001_init, ..., 0007_monitor_detail; 7 migrations recorded
uv run python -m api.migrate                              # again: "applied nothing new"
unset PH_DATABASE_URL
```

(Same thing without a local checkout: `docker run --rm -e PH_DATABASE_URL planet-hunter-api python -m api.migrate`.)

### B3. Render deploy

If the Blueprint was created before `main` had `render.yaml`, or to redeploy by hand: Render
dashboard → **planet-hunter-api → Manual Deploy → Deploy latest commit**. Then:

```sh
curl -fsS "$API/healthz"                          # {"ok":true} (allow ~60 s if it was asleep)
curl -fsS "$API/finder/funnel" | head -c 300; echo
curl -fsS "$API/monitor/now"; echo
```

### B4. Vercel environment and deploy

If `NEXT_PUBLIC_API_BASE` was not set in A3 (or the API URL changed):

```sh
cd web
npx vercel@latest login                 # GitHub, in the browser
npx vercel@latest link                  # pick the planet-hunter project (Root Directory = web)
npx vercel@latest env ls
printf '%s' "$API" | npx vercel@latest env add NEXT_PUBLIC_API_BASE production
npx vercel@latest --prod                 # or Redeploy in the dashboard; NEXT_PUBLIC_* needs a rebuild
```

### B5. Smoke checks

```sh
# CORS: the API must answer the site's origin
curl -si -X OPTIONS "$API/finder/candidates/1_1/vote" \
  -H "Origin: $SITE" -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: x-voter-key" | grep -i '^access-control-allow-origin'
# -> access-control-allow-origin: https://planet-hunter.vercel.app

# The token-protected endpoints are on, and refuse a wrong token (403, not 404)
curl -s -o /dev/null -w '%{http_code}\n' -X POST "$API/monitor/progress" \
  -H 'Authorization: Bearer wrong' -H 'Content-Type: application/json' -d '{}'
# The site loads and is not in demo mode (no "stand-in" wording on the finder page)
curl -fsS "$SITE" -o /dev/null -w '%{http_code}\n'
curl -fsS "$SITE/candidates" | grep -ci 'stand-in' || true    # expect 0
```

Then open `$SITE` in a browser, open the developer console, and check there are no CORS errors.

### B6. The Oracle server

```sh
runner/deploy.sh <server-ip> ~/.ssh/oracle-planet-hunter.key --ref main --api-url "$API"
# it asks for PH_INGEST_TOKEN (typed, not shown); it goes to /etc/planet-hunter.env (root, chmod 600)
ssh -i ~/.ssh/oracle-planet-hunter.key ubuntu@<server-ip> planet-hunter status
```

The server's settings are:
- `/etc/planet-hunter.conf`: `PH_API_URL` (the API URL), `PH_REPO_REF` (`main`), and
  `PH_WORKERS`, which defaults to the server's core count (2 on a 2-OCPU instance, see A4).
- `/etc/planet-hunter.env` (secrets): only `PH_INGEST_TOKEN`, the same value as on Render. The server
  has **no database URL**: it sends each night to the API over HTTPS (`POST /finder/ingest` with that
  token), and runs the pixel checks itself. The database password never leaves Supabase and Render.

After the first run has posted, `curl -fsS "$API/monitor/now"` shows `"mode":"live"` while it runs, and
`"runner": {"state": "searching", ..., "responding": true}`. Between runs `runner.state` is `idle` with
`next_run_at`; `responding: false` means the server stopped answering (see `planet-hunter status` on it).

---

## Part C: cost: everything free

| Service | Plan | Free limits (as documented, checked 27 Sep 2026) | What happens at the limit |
|---|---|---|---|
| **Supabase** | Free | 500 MB database, 5 GB egress, 2 active free projects. **Paused after 1 week of inactivity.** | Paused projects stop answering until you click **Restore** in the dashboard. Our API queries it on every page view and the server posts nightly, so a week without any activity is unlikely while the search runs. |
| **Render** | Free web service | 750 free instance hours per workspace per month (one service running all month is ~744 h). **Sleeps after 15 min without traffic**; the next request waits about a minute. No persistent disk (we don't need one). Bandwidth and build minutes count against monthly included amounts. | Without a card: free services are **suspended** until next month. **With a card on file, Render bills overages.** |
| **Vercel** | Hobby | Personal, **non-commercial** use only. 100 GB Fast Data Transfer, 1M function invocations, 4 active-CPU hours, 5,000 image transformations per month (and more, see their table). | Usage over a limit pauses that feature until 30 days pass. Hobby has no billing, so it cannot charge. |
| **GitHub Actions** | Free | Free for public repositories on standard GitHub-hosted runners. | A **private** repository would use the 2,000 free minutes a month and then need payment or stop. |
| **Oracle Cloud** | Always Free | A1: 1,500 OCPU h + 9,000 GB h per month (= **2 OCPUs, 12 GB** running all month); 200 GB block storage in total (boot volumes included); 10 TB outbound a month. | On a Free Tier account, anything beyond Always Free can only use the 30-day trial credit ($300), then stops. |

**Things that could ever cost money: avoid them.**
1. **Adding a payment card to Render.** Then overages (bandwidth, build minutes) are billed instead
   of pausing the service. Also: `render.yaml` must keep `plan: free`; without `plan`, Render creates
   a paid instance.
2. **Upgrading Vercel to Pro** (a trial offer appears in the dashboard) or adding paid add-ons
   (password protection, more analytics). Hobby itself cannot bill. Commercial use breaks the Hobby
   terms (for example, ads or selling something through the site).
3. **Upgrading Supabase to Pro**, or enabling paid add-ons such as the **IPv4 add-on**, compute
   upgrades, or point-in-time recovery. We use the session pooler precisely so the IPv4 add-on is
   not needed.
4. **Oracle: upgrading to Pay As You Go.** After the upgrade, Always Free resources stay free, but
   anything above them is billed to the card you gave at sign-up: e.g. an A1 instance larger than
   the free OCPU/memory hours, more than 200 GB of volumes, extra volume backups, a second
   instance. On a Free Tier (not upgraded) account these can't be billed; they are stopped when the
   trial credit ends.
5. **Oracle idle reclamation** (not a charge, but you'd lose the server): Oracle may reclaim an
   Always Free instance if, over 7 days, its CPU (95th percentile), network and memory use are all
   under 20%. The runner keeps the cores busy about 21 hours a day, so this should not happen while
   the search runs. If you pause the search for more than a few days (`planet-hunter pause`), expect
   this risk.
6. **Custom domains.** Using the free `*.onrender.com` and `*.vercel.app` addresses costs nothing.
   Buying a domain costs money (from any registrar); attaching one you already own is free on both.
7. **Making the GitHub repository private** (see the table).

Sources: Render free tier <https://render.com/docs/free>, Render Blueprint spec
<https://render.com/docs/blueprint-spec>; Supabase pricing <https://supabase.com/pricing> and
connection guide <https://supabase.com/docs/guides/database/connecting-to-postgres>; Vercel Hobby
<https://vercel.com/docs/plans/hobby>; Oracle Always Free
<https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm> and
<https://www.oracle.com/cloud/free/faq/>; GitHub Actions billing
<https://docs.github.com/en/billing/concepts/product-billing/github-actions>. Plans change: re-check
these pages before relying on a number.

---

## Reference

- **API environment** (full list in `api/README.md`): `PH_DATABASE_URL`, `PH_INGEST_TOKEN`,
  `PH_ADMIN_TOKEN`, `PH_WEB_ORIGIN` (CORS, comma-separated origins), `PH_TRUSTED_PROXY_HOPS=1` on
  Render (per-IP rate limits), `PH_DB_POOL_MAX`.
- **Image:** `api/Dockerfile`, context `api/` only. Python 3.12 slim + uv, installs the API without the
  `finder` extra (no pixels/, astropy or lightkurve; about 270 MB). Listens on `$PORT` (Render sets it).
  Build and run locally:
  ```sh
  docker build -t planet-hunter-api api
  docker run --rm -p 8000:8000 -e PORT=8000 planet-hunter-api      # SQLite inside the container
  ```
- **Website:** no `vercel.json` is needed. Vercel settings: Root Directory `web`, Framework Next.js,
  env `NEXT_PUBLIC_API_BASE` (unset = demo mode).
- **CI:** `.github/workflows/ci.yml` runs on every push and pull request: api (with a Postgres 16
  service), hunt, vet, faint, pixels, pipeline, runner, web (lint, typecheck, test, build), and a build +
  `/healthz` check of the API image. All tests are offline.

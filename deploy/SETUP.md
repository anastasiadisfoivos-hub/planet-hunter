# Going live: step by step

Everything here is **FREE** and asks for **no credit card**. If any screen asks for card or
payment details, **stop**. That means something changed; don't enter one.
Why these hosts: [HOSTING.md](HOSTING.md).

Where things run:

```
browser ──> Vercel Hobby (web/, static Next.js) ──── SUPABASE_URL + SUPABASE_ANON_KEY ──┐
               │  NEXT_PUBLIC_API_BASE  (+ the user's Supabase JWT)                     │
               ▼                                                                        ▼
            Render Free: image ghcr.io/…/planet-hunter-api  ── PH_DATABASE_URL ──> Supabase Free
               ▲   (api/ + pipeline/ sources/ forecast/, TESS cache                (Postgres + Auth)
               │    pre-warmed for WASP-18, WASP-121, WASP-43, TOI-700)                 ▲
GitHub Actions:  image.yml   build + push image, call Render deploy hook               │
                 nightly.yml api.nightly (daily, also keeps Supabase awake) ────────────┘
                             heatmap build ──> branch heatmap-data/heatmap.json ──> web/
```

Names used below (change them if you like, but keep them consistent):
- GitHub repo `anastasiadisfoivos-hub/planet-hunter`
- API image `ghcr.io/anastasiadisfoivos-hub/planet-hunter-api:latest`
- Render service `planet-hunter-api`, so the API URL is `https://planet-hunter-api.onrender.com`
- Vercel project `planet-hunter`, so the site URL is `https://planet-hunter.vercel.app`
- Supabase project `planet-hunter`, region Frankfurt; `<ref>` below is its project ref

Steps marked **(Claude can do)** can be done from the terminal once you have logged in to that
CLI yourself. Tokens never go into the repo or the chat.

## Every env var and secret, and where it goes

| Name | Value | Goes to | Secret? |
|---|---|---|---|
| `PH_DATABASE_URL` | Supabase **session pooler** string (port **5432**) | Render; GitHub Actions secret | **secret** |
| `SUPABASE_URL` | `https://<ref>.supabase.co` | Render (api) | public |
| `SUPABASE_JWKS_URL` | `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` | Render (api) | public |
| `SUPABASE_SERVICE_ROLE_KEY` | a **secret key** (`sb_secret_…`), not the legacy `service_role` JWT | Render (api) **only** | **secret** |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` | Vercel (web) | public |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the **publishable key** (`sb_publishable_…`), not the legacy `anon` JWT | Vercel (web) | public |
| `NEXT_PUBLIC_API_MOCK` | `false` | Vercel | public |
| `NEXT_PUBLIC_API_BASE` | `https://planet-hunter-api.onrender.com` | Vercel | public |
| `PH_ADAPTERS`, `PH_CORS_ORIGINS`, `PH_MAX_CONCURRENT_HUNTS`, `PH_HUNT_TIMEOUT_S`, `PH_SWEEP_TIMEOUT_S` | see step 3 | Render | public |
| `RENDER_DEPLOY_HOOK_URL` | Render → service → Settings → Deploy Hook | GitHub Actions secret | **secret** |
| `PH_IMAGE_ENABLED`, `PH_NIGHTLY_ENABLED`, `PH_HEATMAP_ENABLED` | `true` when ready (step 5) | GitHub Actions variables | public |

- Next.js only exposes variables prefixed `NEXT_PUBLIC_` to the browser. So on Vercel,
  `SUPABASE_URL` / `SUPABASE_ANON_KEY` are named `NEXT_PUBLIC_SUPABASE_URL` /
  `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Confirm the exact names with the SKYMAP session when it adds
  sign-in.
- The API-side names (`SUPABASE_URL`, `SUPABASE_JWKS_URL`, `SUPABASE_SERVICE_ROLE_KEY`) must
  match what the TRAPS session reads.
- **Never** put `SUPABASE_SERVICE_ROLE_KEY` or `PH_DATABASE_URL` on Vercel or in anything named
  `NEXT_PUBLIC_*`.
- **Key names vs key values:** Supabase is retiring the legacy `anon` / `service_role` keys by the
  end of 2026. We keep those names for the variables but store the **new** publishable / secret
  keys in them. supabase-js accepts either.

---

## 0. Before Sunday: code that must be on `main` (FREE)

1. Merge into `main` the branches that are ready: `traps` (api/ + contracts/) first, then
   `deploy`, then `pipeline`, `rubin` (sources/), `forecast`, `skymap` (web/). Use PRs, so
   `ci.yml` checks each one.
   - Render, Vercel and the image build all start from `main`.
2. **Blocker for keeping data:** api/ stores everything in SQLite, and Render Free wipes its disk
   every time the service sleeps. The TRAPS session needs to add a Postgres `Storage` using
   `PH_DATABASE_URL`, used whenever that variable is set.
   - That storage must connect through the session pooler.
   - If it ever uses transaction mode (port 6543), prepared statements must be turned off.
   - Without it, the site works but data resets whenever the API sleeps. Launch labelled as a
     demo, or wait.
3. **Accounts:**
   - api/ verifies Supabase JWTs with `SUPABASE_JWKS_URL` (TRAPS session);
   - web/ adds sign-in with supabase-js (SKYMAP session).
4. For real data rather than fakes, `api/src/api/adapters/real.py` must be wired to the siblings
   (TRAPS). Until then keep `PH_ADAPTERS=fake`.

## 1. Supabase: database + accounts (FREE, no card)

1. Go to https://supabase.com/dashboard → **Sign up** → **Continue with GitHub**. Organization plan:
   **Free**.
2. **New project**:
   - Name `planet-hunter`
   - Region **Central EU (Frankfurt)**, the same as Render in step 3
   - Generate a strong database password and keep it in a password manager
3. **Connection string:** click **Connect** (top bar) → **Session pooler** → copy the URI:
   `postgresql://postgres.<ref>:[YOUR-PASSWORD]@aws-0-eu-central-1.pooler.supabase.com:5432/postgres`.
   Put the password in. This is `PH_DATABASE_URL`.
   - Don't use "Direct connection": it's IPv6-only on Free, and Render can't reach it.
4. **Keys:** **Project Settings → API Keys**. Copy:
   - the **Publishable key** (`sb_publishable_…`), which becomes `SUPABASE_ANON_KEY`;
   - a **Secret key** (`sb_secret_…`, create one if none is listed), which becomes
     `SUPABASE_SERVICE_ROLE_KEY`. Treat it like a password.
5. **JWT signing keys:** **Project Settings → JWT Keys**. Make sure the current key is
   **asymmetric** (ECC P-256 or RSA).
   - If it shows only a legacy HS256 secret, click **Migrate JWT secret** → rotate to the new key.
   - Otherwise `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` returns no keys and the
     API can't verify users.
   - Check it: `curl https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` should show a `keys`
     list that is not empty.
6. **Email sign-in:** **Authentication → Sign In / Providers → Email**. Enable **Email**.
   - The built-in mailer sends only 2 mails an hour, and only to your team, so turn **Confirm
     email OFF** for launch. Otherwise public users can't finish signing up.
   - Later, **Authentication → SMTP Settings** can use a free SMTP provider. Check it needs no card.
7. **URL configuration:** **Authentication → URL Configuration**:
   - Site URL `https://planet-hunter.vercel.app`
   - also add `http://localhost:3000` under Redirect URLs
8. **Staying awake:** Free projects pause after a week without database activity.
   - `nightly.yml` touches the database daily once `PH_NIGHTLY_ENABLED=true` (step 5).
   - If you get the "project will be paused" e-mail, open the site or run the nightly job by hand.
   - A paused project is restored from the dashboard with its data.

## 2. GitHub: build the API image once (FREE) (Claude can do with `gh`)

1. Repo → **Actions** → **image** → **Run workflow** (branch `main`). This takes ~5–10 min.
   - It builds the image with the four "Known systems" stars' TESS data inside.
   - It checks those stars hunt with the network turned off.
   - It pushes `ghcr.io/anastasiadisfoivos-hub/planet-hunter-api:latest`.
2. Make the image public (once): your GitHub profile → **Packages** → `planet-hunter-api` →
   **Package settings** → **Change visibility** → **Public**.
   - Render pulls public images without credentials.
   - Check it from a logged-out terminal:
     `docker pull ghcr.io/anastasiadisfoivos-hub/planet-hunter-api:latest`.

## 3. Render: the API (FREE, no card)

1. Go to https://dashboard.render.com → **Sign up with GitHub**. When asked about billing, skip or
   close it. Don't add a card.
2. **New +** → **Web Service** → **Existing Image**.
   - Image URL: `ghcr.io/anastasiadisfoivos-hub/planet-hunter-api:latest`, no credentials.
   - Name: `planet-hunter-api`
   - Region: **Frankfurt (EU Central)**
   - Instance Type: **Free**
   - **If Render won't allow an existing image on Free:** use **Build and deploy from a Git
     repository** instead. Language **Docker**, branch `main`, Dockerfile Path
     `./deploy/Dockerfile`, Docker Build Context Directory `.`. Add the env var
     `PREWARM_STARS=WASP-18,WASP-121,WASP-43,TOI-700`; Render passes it to the build. Every
     deploy then uses Render's 500 free build minutes a month, so turn Auto-Deploy **off**.
3. **Advanced** → Health Check Path: `/healthz`.
4. **Environment Variables**:

   | Key | Value |
   |---|---|
   | `PH_ADAPTERS` | `fake` (`real` once the adapters are wired) |
   | `PH_CORS_ORIGINS` | `https://planet-hunter.vercel.app` (the exact Vercel URL from step 4; comma-separate several) |
   | `PH_MAX_CONCURRENT_HUNTS` | `1` (512 MB RAM) |
   | `PH_HUNT_TIMEOUT_S` | `600` (0.1 CPU: an uncached 2-sector hunt takes ~3 min) |
   | `PH_SWEEP_TIMEOUT_S` | `30` |
   | `PH_DATABASE_URL` | the session-pooler string from step 1.3 |
   | `SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `SUPABASE_JWKS_URL` | `https://<ref>.supabase.co/auth/v1/.well-known/jwks.json` |
   | `SUPABASE_SERVICE_ROLE_KEY` | the secret key from step 1.4 |

   Don't set `PORT`: Render sets it, and the image listens on `$PORT`.
5. **Deploy Web Service**. Then **Settings → Deploy Hook** → copy the URL. It is a secret; it goes
   in GitHub in step 5.
6. Check: `curl https://planet-hunter-api.onrender.com/healthz` should give `{"ok":true}`.
   - The first request after a sleep takes ~1 min.
   - API docs: `https://planet-hunter-api.onrender.com/docs`.

## 4. Vercel: the web site (FREE, no card) (Claude can do, after `npx vercel login`)

1. Go to https://vercel.com/signup → **Hobby** → **Continue with GitHub**.
2. **Add New…** → **Project** → import `anastasiadisfoivos-hub/planet-hunter`.
3. Configure:
   - Project Name: `planet-hunter`
   - Framework Preset: **Next.js**
   - Root Directory: **`web`**
4. **Environment Variables** (all environments):

   | Key | Value |
   |---|---|
   | `NEXT_PUBLIC_API_MOCK` | `false` |
   | `NEXT_PUBLIC_API_BASE` | `https://planet-hunter-api.onrender.com` |
   | `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the publishable key from step 1.4 |

   These are baked in at build time, so after changing them, redeploy (Deployments → ⋯ → Redeploy).
5. **Deploy**. If the URL isn't `https://planet-hunter.vercel.app`, update:
   - Render `PH_CORS_ORIGINS`;
   - Supabase Site URL (step 1.7).
6. Hobby is for non-commercial use: no ads, no paid features.

## 5. GitHub: secrets and switches (FREE) (Claude can do with `gh`)

Repo → **Settings** → **Secrets and variables** → **Actions**.

1. **Secrets**:
   - `PH_DATABASE_URL`: the session-pooler string (step 1.3)
   - `RENDER_DEPLOY_HOOK_URL`: from step 3.5
2. **Variables**:

   | Name | Value | When |
   |---|---|---|
   | `PH_IMAGE_ENABLED` | `true` | Now. Rebuilds the pre-warmed image nightly and on every push to `main`, then redeploys Render. |
   | `PH_HEATMAP_ENABLED` | `true` | Once `sources/` is on `main` |
   | `PH_NIGHTLY_ENABLED` | `true` | Once api/ has Postgres storage (step 0.2). It also keeps Supabase from pausing. |
   | `PH_ADAPTERS` | `real` | Once the real adapters are wired (step 0.4) |
   | `PH_PREWARM_STARS` | optional; default `WASP-18,WASP-121,WASP-43,TOI-700` | Only if the "Known systems" list changes |

   From the terminal (the values are pasted at the prompt, never typed into the command):
   ```sh
   R=anastasiadisfoivos-hub/planet-hunter
   gh secret set PH_DATABASE_URL -R $R
   gh secret set RENDER_DEPLOY_HOOK_URL -R $R
   gh variable set PH_IMAGE_ENABLED -b true -R $R
   gh variable set PH_HEATMAP_ENABLED -b true -R $R
   ```
3. Test by hand: **Actions** → **nightly** → **Run workflow**.
   - "dry run" is ticked by default.
   - The heatmap job pushes `heatmap.json` to the `heatmap-data` branch, served at
     `https://raw.githubusercontent.com/anastasiadisfoivos-hub/planet-hunter/heatmap-data/heatmap.json`.
4. Schedules: `image` runs at 08:47 UTC and `nightly` at 09:17 UTC.
   - GitHub pauses schedules after 60 days with no commits.
   - If that happens, click **Enable workflow** on the Actions tab.

## 6. Final checks (FREE)

1. `curl https://planet-hunter-api.onrender.com/healthz` gives `{"ok":true}`.
2. Open `https://planet-hunter.vercel.app`:
   - sign up with an e-mail + password;
   - open a "Known systems" star. Nothing gets downloaded, but at 0.1 CPU it still takes ~1–2 min
     (see HOSTING.md, "Making Known systems instant");
   - place a sky watch.
3. Browser devtools → Network: no CORS errors. If there are, fix `PH_CORS_ORIGINS`.
4. Actions tab: `ci`, `image` and `nightly` are green on `main`.

## Still needed from other sessions (not deploy's area)

- **api/ (TRAPS):**
  - Postgres `Storage` using `PH_DATABASE_URL` through the session pooler;
  - verifying Supabase JWTs with `SUPABASE_JWKS_URL`;
  - real adapters.
- **web/ (SKYMAP):**
  - sign-in with supabase-js, reading `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY`;
  - read the heatmap from `NEXT_PUBLIC_HEATMAP_URL` (raw.githubusercontent.com sends
    `Access-Control-Allow-Origin: *`);
  - a "waking up (~1 min)" state while the API sleeps.
- **sources/ (RUBIN):** the README's `skysources-heatmap` command isn't declared in
  `pyproject.toml` yet. The workflow uses `python -m skysources.heatmap`.

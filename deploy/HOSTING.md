# Hosting on free tiers

Researched **2026-09-25**. Rule for this project: **free tier only, and never a plan that asks for a
credit card or any payment details**, even a "verification" card. Free-tier terms change
often, so re-check the linked pages before relying on a number.

## What the backend actually needs (measured)

Measured with `deploy/Dockerfile` on 2026-09-25, running a real `python -m hunter WASP-18
--max-sectors 2` (2 TESS sectors downloaded from MAST) inside the container:

| Setup | Peak RAM | Wall time |
|---|---|---|
| API only, fakes on (import + idle) | 45 MB | – |
| API + pipeline + sources + forecast imported | 265 MB | – |
| Real 2-sector hunt, 2 GB / 2 CPU | 276 MB | 30 s |
| Real 2-sector hunt, **512 MB / 1 CPU** | 278 MB | 28 s |
| Real 2-sector hunt, **512 MB / 0.1 CPU** (Render Free size) | 278 MB | **170 s** |
| Same, **cache pre-warmed, network off** (image.yml): WASP-18 / WASP-121 / WASP-43 / TOI-700 | – | 79 / 52 / 61 / 124 s |

So the earlier "1–2 GB" estimate was too high for a 2-sector hunt: one hunt fits in 512 MB with
room to spare. **CPU**, not RAM, is the limit on the smallest free machines: at 0.1 CPU a hunt
takes ~3 min instead of 30 s. That is inside the API's default 300 s hunt timeout, but with little
margin, so raise it to 600 s. Hunts with more sectors take longer. Two hunts at once
(`PH_MAX_CONCURRENT_HUNTS=2`) could reach ~500 MB, so on a 512 MB host set it to `1`.

Image size: 234 MB (API only), 1.37 GB (with all siblings).

## Backend comparison

| Host | Free size | Sleeps? | Disk | Hour cap | Card needed? | Verdict |
|---|---|---|---|---|---|---|
| **Hugging Face Spaces**, Docker, CPU Basic | 2 vCPU, 16 GB RAM, 50 GB | after 48 h idle | wiped on restart | none | **Yes, in effect.** Creating a Docker Space now requires a paid plan (PRO, $9/mo) [1][2] | Best hardware, but **not free any more for Docker**. Ruled out. |
| **Render** Free web service | 0.1 CPU, 512 MB [3] | after 15 min idle, ~1 min to wake [4] | wiped on every redeploy / restart / spin-down; no disks on Free [4] | 750 instance-h/month per workspace [4] | **No.** Without a card, Render disables the service instead of charging [5] | **Recommended.** The only card-free option that runs the image. |
| **Fly.io** | – | – | – | – | **Yes.** "All organizations … require a credit card on file" [6] | Ruled out. |
| **Koyeb** Free | 0.1 vCPU, 512 MB, 2 GB SSD, 1 per org; scales to zero after 1 h [7] | yes | no volumes | – | **Yes.** Card + $29 pre-auth hold [8] | Ruled out. |
| **Railway** | trial: $5 / 30 days, 1 GB RAM; then $1/mo credit [9][10] | – | – | credit-limited | unclear for the trial | A trial, not a free tier. Ruled out. |
| **Google Cloud Run** | 180k vCPU-s, 360k GB-s / month [11] | scales to zero | ephemeral | per-second quota | **Yes.** Needs a billing account with a card [11] | Ruled out. |

## Database and accounts: Supabase Free

The API stores data in **SQLite** today. On every free host the disk is wiped, so data only
survives in a hosted database. **The API has no Postgres storage yet** (see "What's missing" below).

The site is adding accounts (email + password), so **one free Supabase project provides both
Postgres and Auth**.

| | Supabase Free (chosen) | Neon Free (DB only, for comparison) |
|---|---|---|
| Database | 500 MB, shared CPU, 500 MB RAM [13] | 0.5 GB per project [12] |
| Auth | 50,000 monthly active users [13] | – (no auth) |
| Egress | 5 GB + 5 GB cached [13] | – |
| File storage | 1 GB [13] | – |
| Projects | 2 active; paused ones don't count [13][14] | 100 [12] |
| Idle behaviour | **paused after 1 week of inactivity**. "A few user requests to the database each day" prevent it. There is a warning e-mail ~1 week before. Restore from the dashboard; data is kept [14] | scales to zero after 5 min, wakes itself [12] |
| Card | **No** for the Free plan: "without first needing to put down a credit card" [15]. Paid plans need one. | No [12] |

### Connecting from the API

- Use the **shared pooler (Supavisor)**. On the Free plan the direct connection is **IPv6 only**,
  and the pooler is IPv4 [20].
- For a long-running server like ours, Supabase recommends **session mode (port 5432)** [20].
  Transaction mode (port 6543) is for serverless, and "does not support prepared statements".
- `PH_DATABASE_URL` = the **session-mode pooled** string:
  `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.

### Keys and verifying users

- Supabase now has **publishable** (`sb_publishable_…`) and **secret** (`sb_secret_…`) keys.
  The legacy `anon` / `service_role` keys are **deprecated "by the end of 2026"** [21].
- We keep the env var names `SUPABASE_ANON_KEY` and `SUPABASE_SERVICE_ROLE_KEY`, but they should
  hold the **new** keys:
  - `SUPABASE_ANON_KEY` = the publishable key;
  - `SUPABASE_SERVICE_ROLE_KEY` = a secret key.
  Legacy keys would stop working within months.
- The API verifies user JWTs against the JWKS endpoint:
  `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`.
  That endpoint "does not return any keys if you are not using **asymmetric JWT signing keys**" [22].
  So in the project, **JWT signing keys must be asymmetric** (the default for new projects is
  UNVERIFIED; SETUP.md step 1 checks it).

### Email: the catch for email + password sign-up

Supabase's built-in email sender sends **2 messages per hour**, and only to addresses **on the
project's team**. It is for demos, not production [23]. With it:

- public users can't receive sign-up confirmation mails;
- public users can't receive password-reset mails.

Choices, both free:

1. **Turn off "Confirm email"** (Auth → Sign In / Providers → Email). Accounts work immediately,
   but password reset still can't e-mail a public user.
2. **Connect a free SMTP provider** under Auth → SMTP Settings. Several have card-free free
   tiers, but I have **not verified** any of them. Check that it asks for no card before signing up.

Launch with option 1 unless password reset is needed on day one.

## Front end: Vercel Hobby

- Allowed use: Hobby is "restricted to non-commercial personal use only". Ads, payments or selling
  count as commercial. Donations don't [16]. A free public hobby site with no ads is fine.
- Limits per month [17]:
  - 100 GB Fast Data Transfer
  - 1 M function invocations
  - 4 h of active CPU
  - functions run for at most 300 s
  - going over pauses the feature; it never bills
- Card: not needed. Hobby has no billing cycle; a card is asked for only when upgrading to Pro [17].
- Our web/ build is fully static right now (`next build` output: "prerendered as static content").
  It uses almost none of the function quota.

## Nightly job and heatmap: GitHub Actions

The repo is **public**, so standard GitHub-hosted runners are free with no minute cap. Jobs
can run up to 6 h each [18]. Scheduled work runs there, not on the web host; Render's free plan
has no cron jobs.

- `nightly.yml`: `api.nightly` and the heatmap build.
- `image.yml` (nightly and on push to `main`):
  - builds the API image with the TESS cache **pre-warmed** for the "Known systems" stars
    (WASP-18, WASP-121, WASP-43, TOI-700);
  - pushes it to GitHub Container Registry (free for public images);
  - triggers Render's deploy hook.

The cache is inside the image, so Render's disk wipes don't lose it. Render doesn't build
anything, which saves its 500 free build minutes a month; with no card, builds stop when those
run out [24]. Render can deploy a public registry image without credentials [25].

- Whether *image-backed* services and deploy hooks are allowed on the **Free** instance type is
  **UNVERIFIED**: the docs don't restrict them, but don't say so either.
- If Render refuses, the fallback is to build from the repo with `PREWARM_STARS` set as a Render
  env var. Render passes env vars to Docker builds as build args [26]. That costs Render build
  minutes on every deploy.

## Recommendation

**Render Free (Docker) for the API + Supabase Free for Postgres and Auth + Vercel Hobby for
web/ + GitHub Actions for nightly, heatmap and the pre-warmed image.** None of these asks for a card.

The first choice would have been Hugging Face Spaces (16 GB, 2 vCPU, free). Since July 2026 it
needs PRO to create a Docker Space, so it is out under the no-card rule. Render is the next best
card-free option.

## What breaks on each free tier

| Service | What breaks | What we do about it |
|---|---|---|
| Render Free | Sleeps after 15 min idle; the first visitor waits ~1 min | The web app shows a "waking the telescope…" state. (web/'s job; its API client already polls.) |
| Render Free | **Disk wiped on every spin-down**, so SQLite traps and catches vanish | Needs the Postgres storage in api/ (see below). Until then, treat live data as demo data. |
| Render Free | 0.1 CPU: a 2-sector hunt takes ~170 s instead of ~30 s | `PH_HUNT_TIMEOUT_S=600`, `PH_MAX_CONCURRENT_HUNTS=1`; the UI already shows job progress |
| Render Free | 512 MB RAM | One hunt peaks at ~280 MB, which fits. Keep concurrency at 1. |
| Render Free | 750 h/month for the workspace | One always-on service would use 720–744 h. Sleeping keeps it well under. Never add a second free service to the same workspace. |
| Render Free | Bandwidth over the free allowance suspends the service for the rest of the month (no card, so no bill) | Serve heatmap.json and static files from GitHub / Vercel, not from the API. |
| Render Free | Hunts are slow (0.1 CPU) | The "Known systems" stars ship with their data cached in the image (`image.yml`). That removes the downloads, but the computation still takes 52–124 s at 0.1 CPU, so they are **not instant**. For instant results, the finished hunt results must be stored ahead of time (see below). |
| Supabase Free | **Paused after 1 week without database activity**, which takes the site down | `nightly.yml` queries the database daily, once `PH_NIGHTLY_ENABLED=true`. The warning e-mail goes to Foivos. |
| Supabase Free | 500 MB database, 5 GB egress | Plenty for traps + catches + accounts. The `raw` blobs are the thing to watch. |
| Supabase Free | Built-in email: 2/hour, team addresses only | Turn off "Confirm email", or add a free SMTP (see above). |
| Supabase Free | Legacy `anon` / `service_role` keys go away by end of 2026 | Use the publishable / secret keys from day one. |
| Vercel Hobby | Non-commercial only | No ads, no paid features. |
| GitHub Actions | Scheduled workflows are disabled after 60 days without repo activity [19] | Any push re-enables them; or click "Enable workflow". |

## Making "Known systems" instant

A warm download cache halves the wait; it doesn't remove it. The CPU work is what's left.
Instant means serving results computed ahead of time. Two ways, neither in deploy's area:

1. **Nightly publishes the results.** `image.yml` already runs the four hunts in CI, on full CPU.
   It could also write each star's `[Discovery]` list (contract shape) to the `heatmap-data`
   branch, next to heatmap.json, and web/ could show them directly. That needs a small web/ change.
2. **The API returns stored results.** If a star was hunted recently, the API returns the stored
   Discoveries from Postgres and only re-hunts when `latest_data_marker` changes. That is api/'s
   call, and needs the Postgres storage first.

## What's missing before data survives a restart

`api/` has a `Storage` port with one implementation, SQLite. For Render + Supabase it needs a
**Postgres `Storage`** that reads a connection string from **`PH_DATABASE_URL`** (the name the
deploy files and SETUP.md use). That lives in `api/`, which is the TRAPS session's area, so it is
requested there, not written here. Everything else is ready: the nightly workflow already passes
`PH_DATABASE_URL`, and SETUP.md puts it on Render. The same goes for accounts: verifying Supabase
JWTs (`SUPABASE_JWKS_URL`) is api/'s work, and the sign-in UI is web/'s.

## Sources (all accessed 2026-09-25)

1. HF, Spaces overview. "Gradio and Docker Spaces run on compute and require a paid plan to create: PRO for personal accounts…" https://huggingface.co/docs/hub/spaces-overview
2. HF pricing (PRO $9/mo, "Host ZeroGPU, Gradio & Docker Spaces"). https://huggingface.co/pricing · forum report of the change (8 Jul 2026): https://discuss.huggingface.co/t/docker-sdk-now-marked-as-paid-when-creating-a-new-space/177580
3. Render compute plans. https://render.com/docs/compute-plans
4. Render free instances. https://render.com/docs/free
5. Render FAQ. "If you haven't added a payment method and you would incur charges, Render instead disables your services…" https://render.com/docs/faq
6. Fly.io pricing. https://docs.fly.io/about/pricing/
7. Koyeb instances (updated 2026-05-27). https://www.koyeb.com/docs/reference/instances
8. Koyeb pricing FAQ (updated 2026-05-27). https://www.koyeb.com/docs/faqs/pricing
9. Railway pricing FAQ. https://docs.railway.com/pricing/faqs
10. Railway free trial. https://docs.railway.com/reference/pricing/free-trial
11. Google Cloud free features (updated 2026-09-24). "A Google Cloud billing account is required…" https://docs.cloud.google.com/free/docs/free-cloud-features
12. Neon pricing. https://neon.com/pricing
13. Supabase pricing. https://supabase.com/pricing
14. Supabase project pausing. https://supabase.com/docs/guides/platform/free-project-pausing
15. Supabase pricing post, "without first needing to put down a credit card". https://supabase.com/blog/pricing. The official docs pages checked don't say it outright, so if sign-up asks for a card, stop.
16. Vercel fair use guidelines (updated 2026-09-14). https://vercel.com/docs/limits/fair-use-guidelines
17. Vercel Hobby plan (updated 2026-09-14). https://vercel.com/docs/plans/hobby
18. GitHub Actions billing and limits. https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions · https://docs.github.com/en/actions/administering-github-actions/usage-limits-billing-and-administration
19. GitHub, disabling and enabling a workflow. https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow
20. Supabase, connecting to Postgres (pooler modes, IPv4/IPv6). https://supabase.com/docs/guides/database/connecting-to-postgres
21. Supabase API keys. "Supabase is deprecating the `anon` and `service_role` keys by the end of 2026." https://supabase.com/docs/guides/api/api-keys
22. Supabase JWTs and the JWKS endpoint. https://supabase.com/docs/guides/auth/jwts
23. Supabase custom SMTP (default sender limits). https://supabase.com/docs/guides/auth/auth-smtp
24. Render build pipeline (Hobby: 500 minutes/month). https://render.com/docs/build-pipeline
25. Render, deploying an image; deploy hooks. https://render.com/docs/deploying-an-image · https://render.com/docs/deploy-hooks
26. Render Docker (env vars become build args; BuildKit). https://render.com/docs/docker

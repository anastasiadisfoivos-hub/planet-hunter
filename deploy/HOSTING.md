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

## Database

The API stores data in **SQLite** today. On every free host the disk is wiped, so data only
survives in a hosted database. **The API has no Postgres storage yet** (see "What's missing" below).

| | Neon Free | Supabase Free |
|---|---|---|
| Storage | 0.5 GB per project [12] | 500 MB [13] |
| Compute | 100 CU-hours per project per month, autoscaling to 2 CU [12] | shared CPU, 500 MB RAM [13] |
| Idle behaviour | scales to zero after 5 min (can't be turned off); wakes on the next query in about a second [12] | **project is paused after 1 week of inactivity** and must be restored [14] |
| Projects | 100 [12] | 2 active [13] |
| Card | **No.** "permanent (not a trial); no credit card required" [12] | No [15] |

**Pick Neon.** A pause after a quiet week would take the site down. Neon's scale-to-zero
wakes automatically.

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
can run up to 6 h each [18]. `api.nightly` and the heatmap build run there
(`.github/workflows/nightly.yml`), not on the web host. Render's free plan has no cron jobs.

## Recommendation

**Render Free (Docker) for the API + Neon Free for Postgres + Vercel Hobby for web/ + GitHub
Actions for nightly and heatmap.** None of these asks for a card.

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
| Neon Free | 0.5 GB storage; 100 CU-h/month | Plenty for traps + catches. The `raw` blobs are the thing to watch. |
| Neon Free | Scale-to-zero cold start on the first query | Negligible next to Render's own wake-up. |
| Vercel Hobby | Non-commercial only | No ads, no paid features. |
| GitHub Actions | Scheduled workflows are disabled after 60 days without repo activity [19] | Any push re-enables them; or click "Enable workflow". |

## What's missing before data survives a restart

`api/` has a `Storage` port with one implementation, SQLite. For Render + Neon it needs a
**Postgres `Storage`** that reads a connection string from **`PH_DATABASE_URL`** (the name the
deploy files and SETUP.md use). That lives in `api/`, which is the TRAPS session's area, so it is
requested there, not written here. Everything else is ready: the nightly workflow already passes
`PH_DATABASE_URL`, and SETUP.md puts it on Render.

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
14. Supabase billing. https://supabase.com/docs/guides/platform/billing-on-supabase
15. Supabase billing FAQ. https://supabase.com/docs/guides/platform/billing-faq
16. Vercel fair use guidelines (updated 2026-09-14). https://vercel.com/docs/limits/fair-use-guidelines
17. Vercel Hobby plan (updated 2026-09-14). https://vercel.com/docs/plans/hobby
18. GitHub Actions billing and limits. https://docs.github.com/en/billing/managing-billing-for-your-products/managing-billing-for-github-actions/about-billing-for-github-actions · https://docs.github.com/en/actions/administering-github-actions/usage-limits-billing-and-administration
19. GitHub, disabling and enabling a workflow. https://docs.github.com/en/actions/managing-workflow-runs-and-deployments/managing-workflow-runs/disabling-and-enabling-a-workflow

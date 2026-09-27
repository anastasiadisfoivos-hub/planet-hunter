# runner/: the nightly Planet Finder search on one always-on server

Everything needed to run the Planet Finder's search every day on an **Oracle Cloud Always Free** server (Ampere A1,
4 cores, 24 GB, Ubuntu 24.04, arm64). It is **not** a GitHub self-hosted runner: the repository is public, so the
server pulls it read-only over HTTPS and runs on its own systemd timer. Nothing listens on the internet except SSH
(key only).

It finds **candidates**, never planets: every candidate still needs people to review it and follow-up observations.

```
runner/
  deploy.sh          run on your Mac: installs / updates the server, asks for the secrets, starts the timer
  bootstrap.sh       run on the server (deploy.sh does it): packages, uv, repo, venvs, systemd, firewall
  sync-venvs.sh      one venv per package (hunt, faint, vet, api), rebuilt only when a lock file changes
  systemd/           planet-hunter.service + planet-hunter.timer
  bin/planet-hunter  the command you use on the server (status, logs, stop, pause, resume, update)
  scheduler/         the scheduler (Python, standard library only): ledger, queues, workers, posting, ingest
  tests/             ledger, queue policy, posting and a whole run against the real API (locally)
  dryrun/            the Ubuntu 24.04 container used to prove the install end to end
```

## Install (once you have the server's IP)

From the repository on your Mac:

```sh
runner/deploy.sh <ip> ~/.ssh/<your-oracle-key>
```

It connects as `ubuntu` (Oracle's default user), runs `bootstrap.sh`, then asks for two secrets. What you type is
not shown:
- `PH_INGEST_TOKEN`: the API's ingest token (the same value as the API's `PH_INGEST_TOKEN` on Render);
- `PH_DATABASE_URL`: the Postgres URL the API uses (Supabase pooler URL).

They go over SSH straight into `/etc/planet-hunter.env` on the server, which is owned by root and set to
`chmod 600`. They are never put on a command line, into a file on your Mac, or into git. Then deploy.sh turns on
the daily timer, starts today's run and shows the status. Options:
- `--ref <branch>`: the branch to run (default `v2`);
- `--api-url`: default `https://planet-hunter-api.onrender.com`;
- `--keep-secrets`: on a re-deploy, keep the secrets already on the server;
- `--no-start`: install without starting;
- `--user`, `--port`: SSH user and port.

In the Oracle console, keep the instance's security list (VCN) at **ingress TCP 22 only**. Give the boot volume
**≥ 200 GB**: the free tier includes 200 GB, and the runner keeps its own data under 150 GB.

## What it does each day

A **run** is one search day, with run id `oracle-YYYYMMDD`. The timer starts it at **00:15 UTC** and also 3 minutes
after every boot. Before each run, `git fetch` + `git reset --hard` bring the clone to the tip of the branch, and any
venv whose lock file changed is refreshed (`PH_AUTO_UPDATE=1`).

1. **Prepare.** The ranked star list (`hunt targets`) is rebuilt if it is older than 7 days. One snapshot of the
   known-planet / TOI / CTOI / EB lists is taken for the whole run.
2. **Search, until 21:45 UTC.** 4 worker processes run, one star each, one BLAS thread each, so the 4 cores stay
   busy (Oracle reclaims idle free machines).
3. **Record every star.** Each finished star:
   - is written to the SQLite **ledger** (`/var/lib/planet-hunter/ledger.sqlite`);
   - is posted to the API: `POST /monitor/progress` with `Authorization: Bearer PH_INGEST_TOKEN` and
     `{run_id, run_started_at, shard, done, total, star}`, where `star` is the monitor record
     (`{tic, tmag, teff, radius_rsun, ra, dec, sectors, observed_from, observed_to, lightcurve: {t, f}, detections,
     outcome, searched_at}`, built from hunt's own result). Each queue is its own shard (fast 0, deep 1, faint 2),
     so the site's progress is their sum.
4. **Heartbeat.** A post every 2 minutes keeps the monitor "live" while long stars run. The API calls a run live if
   it heard from it within 15 minutes.
5. **Vetting.** Every candidate is vetted with **skyvet** (`vet/`: LEO-vetter, TRICERATOPS, Gaia DR3, VSX) on one
   worker as soon as it appears.
6. **Wrap-up.**
   - `hunt merge` runs over the night's queues: ranked candidates, the funnel, and the nearby-stars artefact test for
     single / duo dips.
   - skyvet's `vetting` block is attached to each candidate.
   - `python -m api.finder_ingest` (api's venv, `--extra finder`) runs with `PH_DATABASE_URL`: it stores the
     candidates, pixel-checks them (`pixels/`) and marks the monitor run done. Candidates reach the site at the end
     of each day's run.
   - The run is `done`. A start later the same day exits at once.

### Queue policy

Three search queues each go down their own ranked list. The ledger skips every star already finished.

| Queue | List, in this order | Search |
|---|---|---|
| **fast** | hunt's ranked list (`targets.csv`: known hosts interleaved with new stars; M dwarfs, then small stars, then other dwarfs; smaller, then brighter). It skips a star the deep pass already did on the same sectors. | newest 3 sectors, BLS only (`deep_search=False, dip_search=False`) |
| **deep** | 1. stars the fast pass flagged as **promising**: a candidate, or a periodic signal at SNR ≥ 7 that failed only on SDE, the transit count or a check, best first; 2. DEEPHUNT group 0: ≥ 5 sectors, Tmag ≤ 11, quiet dwarfs; 3. group 1: all other stars with ≥ 5 sectors | every sector stitched: BLS short + long, TLS, single / duo dips |
| **faint** | faint/'s **tier-1 M dwarfs** (Tmag 13–16, ≥ 3 TGLC sectors), in rank order | TGLC light curves, deep search |

**Nightly split.** Each queue has a share of the night's worker-seconds (`PH_SPLIT`):

| Queue | Share |
|---|---|
| fast | 45 % |
| deep | 40 % |
| faint | 15 % |

- When a worker is free, it takes the queue furthest below its share. Running stars count at their expected cost.
- A queue that runs out gives its time to the others.
- Vetting uses at most 1 worker (`PH_VET_SLOTS`).
- Why this split: the fast pass is cheap and moves down the whole list; the deep pass is where long periods and small
  planets come from and feeds the paper route (brighter stars); faint stars give public candidates only (roadmap
  decision 4).

**At 21.5 h × 4 workers**, with the priors from DEEPHUNT and FAINT (60 s / 250 s / 90 s per star per core), that is
about 2,300 fast, 500 deep and 520 faint stars a day. The ledger's measured times replace those priors from the
first night on (see **Measured** below).

### Ledger

`stars(queue, tic)` records:
- `status`: `running`, `done` or `failed`;
- `attempts`;
- `sectors_key`: the sectors the list says the star has;
- times, outcome, counts, and the fast pass's `promising` flag.

A star can be started only if:
- it has no row in that queue; or
- it `failed` fewer than 3 times (timeouts, crashes and network errors are retried); or
- it is `done` on **other sectors**: a new public sector re-queues it.

"No data" is `done`. Claiming is one SQL statement, so a star never runs twice at once. After a crash or reboot,
stars left `running` become retryable without losing an attempt. The run then resumes with the same id and deadline.

### Disk

Everything lives under `/var/lib/planet-hunter`: the ledger, run folders, target lists, and every package's cache
(`HUNTER_CACHE_DIR`, `FAINT_CACHE_DIR`, `SKYVET_*`, `SKYPIXELS_CACHE_DIR`, astropy / lightkurve under `cache/`).
Every 10 minutes the janitor measures it:
- **over 85 % of 150 GB:** it deletes, down to 70 %,
  1. run folders older than 14 nights (their results are in the database by then);
  2. then the least recently used re-downloadable files: MAST FITS, TGLC files, TESScut cutouts.
- **still over 150 GB, or under 5 GB free on the filesystem:** no new star starts until there is room.

journald is capped at 2 GB.

## Is it running?

```sh
ssh -i ~/.ssh/<key> ubuntu@<ip>
planet-hunter status        # tonight's run: state, stars done / planned per queue, vets, monitor posts, disk
planet-hunter logs          # follow the log (journalctl -u planet-hunter -f)
```

`status` reads `/var/lib/planet-hunter/state/heartbeat.json`, which is rewritten every 2 minutes, and the ledger.
It also shows the last run's measured stars per hour and what was ingested. On the site, the monitor shows
**Live** while a run posts, and the replay of the last run otherwise. `/monitor/stats` → `last_run_at`.

## Stop it

- `sudo planet-hunter stop`: stops the current run now. Stars cut off are retried at the next start, and the timer
  still starts tomorrow's run.
- `sudo planet-hunter pause`: stops it **and** turns the timer off, so nothing starts again, not even after a reboot.
- `sudo planet-hunter resume`: turns the timer back on.
- `sudo planet-hunter start`: starts or resumes today's run now.

## Update it

- **Code:** nothing to do. Each run first pulls the branch (`PH_REPO_REF` in `/etc/planet-hunter.conf`) and
  refreshes changed venvs. To do it now: `planet-hunter update` (`--force-sync` rebuilds every venv).
- **Runner scripts / units:** re-run `runner/deploy.sh <ip> <key> --keep-secrets` from your Mac. It is idempotent.
- **Settings:** edit `/etc/planet-hunter.conf` (`PH_WORKERS`, `PH_SPLIT=fast=45,deep=40,faint=15`,
  `PH_DISK_CAP_GB`, `PH_SEARCH_HOURS`, `PH_REPO_REF`, `PH_API_URL`, `PH_AUTO_UPDATE`, ...). They apply at the next
  start.
- **Secrets:** re-run deploy.sh and answer "n" to "keep them?".

## Tests

```sh
cd runner && uv run pytest -q
```

The tests use `tests/fakes/` (a stand-in hunt / skyfaint / skyvet with the real entry points and output shapes, no
network) and the repository's **real** API, served locally with uvicorn on SQLite. They cover:
- the ledger: no repeats, retries, a new sector re-queues a star, resume after a process is killed mid-star;
- the queue policy (order, promotion into the deep queue, the split over a simulated night);
- posting: live monitor, wrong token, API down never blocks;
- the monitor record;
- a whole run through `python -m scheduler run`: live monitor, vetting, merge, `finder_ingest`, run marked done;
- a power cut mid-run (SIGKILL of the scheduler and every star): the restart repeats no finished star.

## Dry run (Ubuntu 24.04 arm64 container)

`dryrun/run_dryrun.sh` builds a systemd + SSH Ubuntu 24.04 container with 4 CPUs and deploys to it with
`deploy.sh`, exactly as to the real server. The container then searches real TESS stars (MAST, TGLC) and posts to
a local copy of the API on Postgres. `finder_ingest` writes to the same Postgres.

Measured on 2026-09-27: see **Measured** below.

## Measured

(filled from the dry run; see the end of this file)

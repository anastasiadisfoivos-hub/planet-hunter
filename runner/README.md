# runner/: the nightly Planet Finder search on one always-on server

Everything needed to run the Planet Finder's search every day on an **Oracle Cloud Always Free** server (Ampere A1,
2 cores, 12 GB, Ubuntu 24.04, arm64: the free amount since Oracle halved it; decided 27 Sep). It is **not** a GitHub self-hosted runner: the repository is public, so the
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
runner/deploy.sh <ip> ~/.ssh/<your-oracle-key> --ref main --api-url https://<the-api>.onrender.com
```

It connects as `ubuntu` (Oracle's default user), runs `bootstrap.sh`, then asks for one secret, `PH_INGEST_TOKEN`:
the API's ingest token (the same value as the API's `PH_INGEST_TOKEN` on Render). What you type is not shown. The
server holds no database URL: everything it stores goes to the API over HTTPS with that token.

It goes over SSH straight into `/etc/planet-hunter.env` on the server, which is owned by root and set to
`chmod 600`. It is never put on a command line, into a file on your Mac, or into git. Then deploy.sh turns on
the daily timer, starts today's run and shows the status. Options:
- `--ref <branch>`: the branch to run (default `main`);
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
2. **Search, until 21:45 UTC.** One worker process per core (`PH_WORKERS`, 2 on the free instance) runs one star
   each, one BLAS thread each, so the cores stay busy (Oracle reclaims idle free machines).
3. **Record every star.** Each finished star:
   - is written to the SQLite **ledger** (`/var/lib/planet-hunter/ledger.sqlite`);
   - is posted to the API: `POST /monitor/progress` with `Authorization: Bearer PH_INGEST_TOKEN` and
     `{run_id, run_started_at, shard, done, total, star, label}`, where `label` is the queue and `star` is the
     monitor record
     (`{tic, tmag, teff, radius_rsun, ra, dec, sectors, observed_from, observed_to, lightcurve: {t, f}, detections,
     outcome, searched_at}`, built from hunt's own result; the curve in 30-min bins, at most 2,000 points). Each queue is its own shard (fast 0, deep 1, faint 2),
     so the site's progress is their sum.
4. **Heartbeat.** Every 2 minutes `POST /monitor/heartbeat` says what the server is doing (searching, vetting,
   ingesting) with the ledger's counts per queue (the site's coverage by queue), and keeps the monitor "live" while
   long stars run. The API calls a run live if it heard from it within 15 minutes. At the end of the run the last
   beat is `idle` with the next run's start, so the site can tell a sleeping server from one that stopped answering.
5. **Vetting.** Every candidate is vetted with **skyvet** (`vet/`: LEO-vetter, TRICERATOPS, Gaia DR3, VSX) on one
   worker as soon as it appears.
6. **Wrap-up.**
   - `hunt merge` runs over the night's queues: ranked candidates, the funnel, and the nearby-stars artefact test for
     single / duo dips.
   - skyvet's `vetting` block is attached to each candidate; a single or duo dip gets a block saying that none of
     skyvet's tools could run without a period (verdict `flag`).
   - `python -m api.remote_ingest` (api's venv, `--extra finder`) sends the night to the API over HTTPS in chunks
     with `PH_INGEST_TOKEN` (`POST /finder/ingest`), which stores the candidates and marks the monitor run done;
     then it runs the pixel checks (`pixels/`) the API asks for (`GET /finder/pixel-queue`) here and posts each
     result. Candidates reach the site at the end of each day's run.
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

**At 21.5 h × 2 workers** (the free instance), with the priors from DEEPHUNT and FAINT (60 s / 250 s / 90 s per star
per core), that is about 1,150 fast, 250 deep and 260 faint stars a day (twice that on 4 cores). The ledger's measured times replace those priors from the
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

Numbers from 2026-09-27: see **Measured** below.

## Measured

Dry run on 2026-09-27 (`dryrun/results_2026-09-27.json`). The setup:
- `deploy.sh` → `bootstrap.sh` on a fresh Ubuntu 24.04.5 arm64 container (systemd, SSH, ufw, 4 CPUs, 7 GB);
- 20 real TESS stars: 14 from hunt's ranked list, 6 tier-1 faint M dwarfs;
- the local API on Postgres 16; the monitor polled every 30 s.

| Queue | Searches | Mean s / star / worker | Stars / hour on 4 workers | Per day at the default split (21.5 h) |
|---|---|---|---|---|
| fast (3 sectors, BLS) | 14 | 36.2 | 398 | ~3,850 |
| deep (all sectors, BLS + TLS + dips) | 11 (6 group-0, 5 promoted by fast) | 270.1 | 53 | ~460 |
| faint (TGLC, deep search) | 6 | 218.1 | 66 | ~210 |

- **Monitor:** "live" for the whole search (44 of 44 polls during it). 103 posts, 0 failed.
- **Results:** 55 signals, 1 candidate (a single dip on TIC 389051009, SNR 28.8: no period, so skyvet and the pixel
  check do not apply). The ingest stored it and marked the run done; the monitor then replays it.
- **Reboot:** after a reboot, the timer started the service, which exited at once: the day's run was done.

Caveats on these numbers:
- the caches were cold;
- the samples are small;
- the host was an Apple-silicon laptop also carrying other work (load ~12 on 10 cores). Ampere A1 cores are slower
  per core than Apple's, so expect the server to be somewhat slower.

The ledger measures every night, and `planet-hunter status` shows the last run's rates.

## For the owner and SHIP (not in runner/)

- **Branches.** The server runs one branch (`PH_REPO_REF`, default `main`, once the release is merged there). That
  branch needs `runner/` plus DEEPHUNT's hunt, `vet/` and `faint/`. The dry run used a local merge of
  `v2 + deephunt + vet + faint + runner`. Merging
  deephunt conflicts in `hunt/README.md` and `hunt/src/hunt/inject.py`; deephunt's side was taken.
- **arm64.** Fixed in the locks (27 Sep): hunt/, faint/ and vet/ lock for Linux aarch64. `batman-package` 2.5.3
  (from transitleastsquares and triceratops) has no Linux arm64 wheel and no sdist, and 2.5.2's sdist builds against
  numpy 1 headers, which fail to import under numpy 2. So on Linux arm64 the locks build batman from upstream's 2.5.3
  source at a pinned commit (its build requires numpy >= 2); elsewhere they use the 2.5.3 wheels. Checked in a
  linux/arm64 container: all three sync frozen and compute a transit model. `sync-venvs.sh` keeps its old
  from-source fallback for refs whose locks predate this. faint's lock now pins DEEPHUNT's hunt too.
- **No monitor writer in hunt.** The runner builds each monitor record itself (`scheduler/monitor_record.py`) from
  hunt's per-star result.

# kaggle/: the daily Planet Finder search in a Kaggle notebook

The same daily search as `runner/`, run in a free **Kaggle notebook** instead of an Oracle server. Kaggle needs no
card, only a phone-verified account (for internet). The search, the queues, the ledger, the monitor posts and
the ingest are RUNNER's scheduler (`runner/scheduler`), unchanged. This folder only adapts it to a notebook
session.

It finds **candidates**, never planets: every candidate still needs people to review it, plus follow-up
observations.

```
kaggle/
  planet_hunter_nightly.ipynb   the notebook you import into Kaggle (settings, secrets, clone, run, summary)
  kaggle_run.py                 what the notebook runs from the clone: restore, guard, install, search, save
  kernel-metadata.json          for the optional `kaggle kernels push` (put your username in it)
  dryrun/                       the local proof: the notebook in a clean container against a local API
```

## Kaggle's limits (checked 27 Sep 2026)

| | Limit | Source |
|---|---|---|
| CPU session | 4 CPU cores, 30 GB RAM | [kaggle.com/docs/notebooks](https://www.kaggle.com/docs/notebooks), Technical Specifications |
| Runtime | 12 h per session (CPU); a saved run must finish in 12 h | same page |
| Disk | 20 GB saved output (`/kaggle/working`); extra scratch disk that is lost after the session | same page |
| Weekly quota | GPU only (30 h/week); no CPU quota documented | [kaggle.com/docs/efficient-gpu-usage](https://www.kaggle.com/docs/efficient-gpu-usage) |
| Schedule | daily, weekly or monthly; CPU notebooks only; not at an exact time ("roughly on the date, UTC"); a limited number of scheduled notebooks (see Active Events) | docs page, "Scheduling Notebooks"; Kaggle staff, [discussion 273569](https://www.kaggle.com/discussions/product-feedback/273569) |
| Internet | Settings > Internet; needs a phone-verified account; secrets need internet on | docs page; [discussion 114053](https://www.kaggle.com/discussions/product-feedback/114053) |
| Terms | the Acceptable Use Policy bans using resources for "server farming" and "activity unrelated to ML data science" | [kaggle.com/aup](https://www.kaggle.com/aup), effective 22 Jun 2025 |

How the notebook fits in 12 hours: **11.5 h** in all (`PH_SESSION_HOURS`), with about 15 min of install and
about 10 h of search. Stars still running when the search window closes get up to 15 min to finish. Then there is
up to 1 h of wrap-up: vetting, merge and ingest. The ledger is saved last. A watchdog stops the search cleanly at
11.5 h if anything runs over. Cut-off stars are retried in the next run.

## Set it up (once)

You need the API's ingest token (the same value as `PH_INGEST_TOKEN` on Render) and the API's address.

1. **Get the notebook.** Download `kaggle/planet_hunter_nightly.ipynb` from GitHub (open the file, then
   **Download raw file**).
2. **Import it.** On kaggle.com: **Create** (left bar) > **New Notebook**. In the editor: **File** >
   **Import Notebook** > drop the `.ipynb` file > **Import**.
3. **Name it.** Click the title at the top left and call it `planet-hunter-nightly`.
4. **Settings** (right-hand panel; if it is hidden, **View** > **Show sidebar**), under **Session options**:
   - **Accelerator:** None (a CPU notebook; only CPU notebooks can be scheduled).
   - **Internet:** on. If Kaggle asks, verify your phone number.
   - **Persistence:** leave as it is. Saved runs do not use it.
5. **Secrets:** **Add-ons** (top menu) > **Secrets** > **Add a new secret**, twice:
   - Label `PH_INGEST_TOKEN`: the ingest token.
   - Label `PH_API_URL`: the API's address, e.g. `https://planet-hunter-api.onrender.com`.

   Tick the **Attached** box next to both, then close the window. Secrets belong to your account, and nothing in
   the notebook prints them.
6. **The ref.** In the notebook's first code cell, set `PH_REPO_REF` to the branch or commit to run. The
   default is `main`. Today `main` holds only the first commit, so until the release is merged into `main`, use
   `kaggle` (the branch with this folder, off `release`) or a commit hash from it. A hash pins the code exactly.
7. **First run.** **Save Version** (top right) > **Save & Run All (Commit)** > **Save**. It runs in the
   background for up to 11.5 h, and you can close the tab. The site's monitor shows **Live** within minutes of
   the search starting. There is no ledger yet, so the log says `no saved state ... starting a new ledger`.
8. **Chain the ledger** (after the first run has finished). Open the notebook in the editor again. In the right
   panel, **Input** > **Add Input** > **Your Work** (or search for `planet-hunter-nightly`) > pick **this same
   notebook** > **+**. Its output (the `ph-state/` folder) now appears under `/kaggle/input/`. Every run loads
   the newest ledger it finds there.
9. **Second run, as the check.** **Save Version** > **Save & Run All** again. In its log, look for:
   `restored /kaggle/input/.../ph-state (saved ... by kaggle-YYYYMMDD): N stars done` (N is the first run's total)
   `guard: the API last heard N stars done; the restored ledger has N`
   If you see `no saved state` instead, or the run stops with `STOP:`, the chaining did not work: see
   **If a run stops** below.
10. **Schedule it.** In the editor's right panel (or on the notebook's page, **Settings** tab) > **Schedule a
    notebook to run** > **Frequency: Daily**, pick a start date > **Save**. The schedule runs the latest saved
    version, including its inputs and secrets. Kaggle picks the time within the day (UTC), and emails you after
    each scheduled run. **Active Events** (the bell icon, top right) lists your scheduled notebooks.

## Is it running? Did it run?

- **The site:** the monitor shows **Live** while a run posts; after it, it replays the last run (`kaggle-YYYYMMDD`).
  `GET <api>/monitor/coverage/queues` gives the ledger's totals per queue from the last heartbeat.
- **Kaggle:** your notebook's page > **Versions** (on the right) or **Logs**. Every scheduled run is a version:
  a green tick means it finished; red means it failed.
- **The last cell** of each version prints what it saved:
  - `run_id`, `state` (`done` when the run finished);
  - `done_total` (all stars ever searched) and `restored_done_total` (what it started from; it must equal the
    previous run's `done_total`);
  - `scheduler_exit` and `error`.
- **The output:** the notebook page > **Output** > `ph-state/`. It holds `manifest.json`, `ledger.sqlite`,
  `targets/` (hunt's ranked list, gzipped) and the small caches.

Run ids: `kaggle-YYYYMMDD` (UTC day of the start). A second run on the same UTC day (for example a manual
**Save & Run All** after the scheduled one) is `kaggle-2-YYYYMMDD` and searches the next stars on the list. It
never repeats the first.

## Update the code

- **The search code** (hunt, vet, faint, runner, this folder): nothing to do on Kaggle if `PH_REPO_REF` is a
  branch. Each run fetches that branch fresh. If it is a commit hash, edit the first code cell to the new hash,
  then **Save Version** (Quick Save is enough; the schedule runs the latest version).
- **The notebook itself** (rare: it only clones the repository and runs `kaggle_run.py`, where the logic lives):
  paste the changed cells into the editor and **Save Version**, or use the CLI below. Afterwards, check that the
  input, the secrets and the schedule are still there.
- **Settings:** add a line like `os.environ["PH_SPLIT"] = "fast=45,deep=40,faint=15"` to the first code cell.
  Every `PH_*` setting from `runner/README.md` applies, except `PH_WORKERS` (default: the cores) and the disk cap
  (default: 70 % of the free scratch disk, at most 150 GB).

### Optional: push new versions with the kaggle CLI (you run it)

```sh
pip install kaggle        # the official CLI, github.com/Kaggle/kaggle-api
# kaggle.com > your picture > Settings > API > Create New Token: saves kaggle.json; put it in ~/.kaggle/ (chmod 600)
# edit kaggle/kernel-metadata.json: replace YOUR-KAGGLE-USERNAME (twice)
kaggle kernels push -p kaggle/          # uploads the notebook as a new version, and runs it
kaggle kernels status YOUR-KAGGLE-USERNAME/planet-hunter-nightly
kaggle kernels output YOUR-KAGGLE-USERNAME/planet-hunter-nightly -p /tmp/ph-state   # download the last output
```

The CLI cannot set a schedule or attach secrets. After a push, open the notebook in the editor once and check
**Add-ons > Secrets** (both attached), **Internet** on, the input (itself) and the schedule. `kernel_sources` lists
the notebook itself. If Kaggle refuses that on push, empty the list and re-attach the input by hand (step 8).

## If a run stops

`STOP: the restored ledger has X finished stars, but the API last heard Y`: the run found no saved ledger, or an
older one, while the API knows more stars were searched. It stops **before searching**, so nothing is searched
twice. It also writes no output, so a later run can still find the last good one.

- Check that the notebook's own output is still attached (**Input** panel, step 8). Kaggle attaches the
  **latest** version's output. Then **Save & Run All**.
- If the last good ledger is only in an older version, download it (notebook page > **Versions** > that
  version > **Output** > download `ph-state/`). Upload it as a private Dataset (**Create** > **New Dataset**),
  add that dataset as an input, and run. The run takes the newest `ph-state/` it finds under `/kaggle/input`.
  After that run, remove the dataset input again.
- To start a new ledger on purpose (every star searched again): add `os.environ["PH_ALLOW_FRESH_LEDGER"] = "1"`
  to the first code cell for one run.

If the install or the search fails, the run still saves the ledger as it was. The next run carries on from
there.

## What each run does

1. **Restore** the newest `ph-state/` under `/kaggle/input`:
   - the ledger (checked against its SHA-256 in the manifest);
   - hunt's ranked list (it keeps its age, so it is rebuilt only when it is 7 days old: `hunt targets` then
     runs at the start of that run and takes time from its search);
   - the small JSON caches;
   - the candidate files of vets still to run.
2. **Guard:** compare the ledger with the API's last heartbeat (above).
3. **Install:** uv, then `runner/sync-venvs.sh` (hunt, faint, vet and api venvs from their locks). The download
   caches are thrown away with the session.
4. **Search** with `python -m scheduler run`: one worker per core (4); the fast, deep and faint queues at the
   usual split; every star recorded in the ledger and posted to `/monitor/progress`; a heartbeat every
   2 minutes; every candidate vetted. It stops starting stars ~1.25 h before the end.
5. **Wrap-up:**
   - `hunt merge`;
   - skyvet's blocks are attached to each candidate;
   - `api.remote_ingest` sends the run to `POST /finder/ingest` with `PH_INGEST_TOKEN` and runs the pixel checks
     the API asks for.
6. **Save** `/kaggle/working/ph-state/`: the next run's input.

## Dry run

`dryrun/run_dryrun.sh <ref> <targets.csv> <faint.csv> <extra.csv> <out>` executes this notebook in a clean
`python:3.11` container (4 CPUs, 7 GB). The container clones GitHub at `<ref>` and posts to the repository's API
served locally on SQLite, which is polled every 30 s. There are three sessions:
- the lists;
- the lists plus 4 new stars, with session 1's output as input;
- no input: it must stop at the guard.

See **Measured** below.

## Measured

Dry run on 2026-09-27 (`dryrun/results_2026-09-27.json`), at ref `79e7627` (branch `kaggle`):
- the notebook executed top to bottom in a clean `python:3.11` container (4 CPUs, 7 GB, linux/arm64);
- 20 real TESS stars: 14 from hunt's ranked list and 6 tier-1 faint M dwarfs, the same lists as `runner/`'s dry
  run;
- the repository's API served locally on SQLite.

| | Session 1 (new ledger) | Session 2 (session 1's output as input, + 4 new stars) | Session 3 (no input) |
|---|---|---|---|
| Install (clone + 4 venvs) | 1.7 min | 2.2 min | – |
| Searches | 31 (14 fast, 11 deep, 6 faint) | 4 (the 4 new stars, fast) | none |
| Repeats of session 1 | – | **0**; all 31 of its ledger rows kept | – |
| Monitor | live for the whole search (23 of 23 polls); 88 posts, 0 failed | 13 posts, 0 failed | – |
| Wrap-up | merge: 1 candidate (a flag after vetting); `/finder/ingest`: created 1, 20 monitor stars; run done | ingest: 4 monitor stars; run `kaggle-2-20260927` done | stopped at the guard (`STOP: ... has 0 finished stars, but the API last heard 35`), **no output written** |
| Session | 18.2 min | 2.7 min | seconds |

Seconds per star per worker in session 1 (cold caches), and what one Kaggle session would do (4 cores, about
10.2 h of search at the 45/40/15 split):

| Queue | This dry run | Stars/hour on 4 cores | Per Kaggle session | With `runner/`'s dry-run times (36 / 270 / 218 s) |
|---|---|---|---|---|
| fast | 23.1 s | 623 | ~2,870 | ~1,830 |
| deep | 146.9 s | 98 | ~400 | ~220 |
| faint | 88.9 s | 162 | ~250 | ~100 |
| **total** | | | **~3,500** | **~2,150** |

Take **~2,000–3,500 stars per daily run** as the range, for these reasons:
- This host's cores are faster than Kaggle's Xeons, and it was less loaded than during `runner/`'s dry run.
- The samples are small, and the caches were cold.
- On the day of the weekly rebuild of hunt's ranked list, `hunt targets` runs first and takes time from the
  search.

The ledger measures every run. The last cell and `manifest.json` (`last_run.stars_per_hour`) show the real rates
from the first Kaggle run on.

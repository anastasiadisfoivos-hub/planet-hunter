# Throughput: stars per night on 20 GitHub Actions runners

Measured 2026-09-26 on a local Mac (10 cores), `--workers 4` to match a standard public-repo `ubuntu-latest`
runner (4 vCPU). The cache started cold, like CI, which caches only `.cache/pipeline/json`, a few kB of query
results, and no FITS. There were 20 stars, rows 101–120 of the 2026-09-26 ranked list (10 list A, 10 list B,
Tmag 8.6–12.8, mixed 2-min and FFI). Both current versions were run: `hunt` (origin/hunt a9efb9c, newest ≤ 3
sectors, BLS) and `deephunt` (origin/deephunt 30bbe36, every sector stitched, short BLS + long BLS + TLS + single
and double dips).

Caveat: another session was running an 8-worker deephunt job on the same machine throughout, so both numbers are
somewhat pessimistic for CPU and network.

## Measured

| | hunt | deephunt |
|---|---|---|
| stars done / timed out | 20 / 0 | 20 / 0 |
| sectors per star | ≤ 3 | 3–8 (mean 5.3) |
| per-star time, mean (median, max) | 53 s (26 s, 178 s) | 223 s (202 s, 597 s) |
| of which fetch / analysis (mean) | 28 s / 26 s | 26 s / 198 s |
| wall time, 4 workers | 13 cold stars in 99 s (pass 2)¹ | 20 stars in 20.85 min |
| local rate, 4 workers | ~270 stars/h (all 20, per-star mean) to ~470 stars/h (pass 2 wall) | **58 stars/h** |

¹ The first hunt pass was interrupted after 7 stars. MAST was slow then, at 106–178 s per star. The rerun
skipped those 7 stars and downloaded its own files (36 for 13 stars), so both halves were cold. The range covers
both.

deephunt's time is **88% CPU** (long BLS 2,201 s, periodic analysis in total 3,930 s, of 4,465 s). hunt's is
about half download.

## Extrapolation to CI

Assumptions:

- A GitHub runner core is about 1.5× slower than this Mac for the CPU part, and the network part is unchanged.
- Each shard gets 350 minutes (5.83 h).
- There are 20 shards and 4 workers each.

| | per star on a runner | per runner per night | **20 runners per night** | best 50,000 targets |
|---|---|---|---|---|
| hunt | 28 + 26×1.5 ≈ 67 s → 4 workers ≈ 215/h | ~1,250 (up to ~2,100 when MAST is quick) | **~25,000 (25k–42k)** | **~2 nights** |
| deephunt | 26 + 198×1.5 ≈ 323 s → 4 workers ≈ 45/h | ~260 (340 at Mac speed) | **~5,200 (5k–6.7k)** | **~10 nights (7–10)** |

"Best 50,000" is the top of the ranked list: all 5,176 M dwarfs, all 17,136 small stars (R★ < 0.8 R☉), then
the first ~27,700 of the 249,510 other dwarfs (targets_2026-09-26_summary.json).

Minutes: 20 × ~355 min, about 7,100 runner-minutes a night. This is free only on a public repository (see
`hunt/ci/sweep.yml`).

## Things that change these numbers

1. **Coverage does not advance night to night as the workflow is written.** `results/` and FITS are not carried
   between runs, and each shard takes rows i, i+20, ... from the top again. Every night re-searches the same top
   ~25k (hunt) or ~5k (deephunt) stars. Covering 50,000 needs one of two changes: persist the list of finished
   TICs (a cache or artifact of `results/*.json` names, which `hunt run` already skips), or pass a nightly offset
   into the ranked list. This is a one-line design decision for the DEPLOY/HUNT sessions; it is not done here.
2. **MAST load:** 80 parallel workers reading from MAST. The first pass saw 2–3 min per star when MAST was slow,
   and the README records MAST stalls mid-read. Expect some nights at the low end.
3. **deephunt is CPU-bound:** time per star grows with the number of sectors. Stars observed in 8 or more
   sectors took up to 10 min. The long-BLS and TLS time budgets (180 s and 60 s) cap the worst case.
4. **A sensible split:** run hunt over the best 50k (about 2 nights), then deephunt only on stars with at least
   5 sectors, where it adds the most (long periods, small planets). That is about 5k stars a night.

## How to reproduce

```bash
git worktree add --detach /tmp/wt origin/hunt && cd /tmp/wt/hunt && uv sync
(head -1 targets.csv; sed -n 102,121p targets.csv) > batch20.csv   # 20 ranked stars
HUNTER_CACHE_DIR=$(mktemp -d) uv run hunt run --tic-file batch20.csv --workers 4 --no-plots --out out
# per-star seconds: results/<tic>.json -> elapsed_s, timings_s
```

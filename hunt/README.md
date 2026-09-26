# hunt: planet-hunter PLANET FINDER

A systematic search of TESS light curves for **new planet candidates**, which people then review in the app.
It outputs candidates only. Nothing here is ever called a planet or a discovery: a candidate needs human
review and follow-up, because a faint background binary and several other things can look the same.

`hunt/` builds on the pipeline package (`../pipeline`, `hunter`) as a path dependency and never edits it.
Anything the pipeline lacks (masking known planets, quality flags, the extra checks, bulk catalogues) is
built here.

```bash
cd hunt && uv sync
uv run hunt targets --out targets                                   # ranked target lists
uv run hunt run --tic-file targets/targets.csv --shard 3/20 --time-budget-min 350 --out shard3
uv run hunt merge shard*/ --tic-file targets/targets.csv --out merged   # ranked candidates + funnel
uv run hunt inject --tic-file targets/targets.csv --out sensitivity.json   # injection-recovery
uv run pytest                                                         # offline, recorded real data
```

## 1. Targets (`hunt targets`)

| List | What | Rule |
|---|---|---|
| A, `targets_new.csv` | new-star search | a SPOC 2-min light curve in the newest public 2-min sector, or a QLP FFI light curve in the newest public QLP sector (`--sectors N` for more); Tmag ≤ 13; **not** a TOI, CTOI, confirmed-planet host (any kind) or TESS EB catalogue star |
| B, `targets_siblings.csv` | sibling search | hosts of confirmed **transiting** planets observed in the same sectors, Tmag ≤ 13 |

- The newest public sectors come from MAST product counts: the highest sector with SPOC 2-min
  time series, and the highest with QLP HLSP light curves.
- Star lists: MAST SPOC observations (2-min) and the QLP target list CSV (FFI, about 1.2 M stars per sector).
- TIC 8.2 parameters (Tmag, Teff, R★, M★, ρ★, luminosity class) for all of them come from one CDS xMatch
  per 50k stars (by position, then TIC-ID equality). This is cached for good.
- Ranking: tier 0 = M dwarf (Teff < 4000 K, dwarf); tier 1 = small star (R★ < 0.8 R☉, dwarf); tier 2 = other
  dwarfs; tier 3 = giants, subgiants and stars with no class. Within a tier, smaller stars come first
  (deeper dips), then brighter ones. Every row carries a plain `reason`.
- `targets.csv` interleaves B and A (one sibling, one new star, ...) for the sweep.
- `targets_summary.json` has the counts at every step.

## 2. Search (`hunt run`)

Each star runs as its own process: fetch (the pipeline's `fetch`: SPOC 2-min > TESS-SPOC > QLP, newest
`--max-sectors`, default 3) → detrend and BLS (the pipeline's `flatten_for_search` and `search`) → checks →
known lists → filter → score.

- **Known hosts (list B):** every listed signal on the star with an ephemeris (confirmed planets, TOIs, CTOIs,
  EB catalogue) is masked before searching: ±0.75 × listed duration plus 3σ of the propagated timing error
  (t0 error and period error × orbits elapsed). Masked points leave both the trend and the search. A planet
  whose timing error exceeds 0.5 d is not masked (this is noted in the output); the known filter still catches it.
- Up to 3 signals per star (two-pass search like the pipeline, then mask and repeat while the last one had
  SNR ≥ 7).
- `--shard i/N` (0-based) takes rows i, i+N, i+2N, ... of the ranked file, so every shard gets top-priority
  stars. The run is resumable: stars already in `results/` are skipped.
- `--time-budget-min M`: a new star starts only if it can plausibly finish before the deadline. A star is
  killed after 5 minutes (MAST sometimes stops answering mid-read) and recorded as `timeout`.

## 3. Checks

Every check has `value`, `passed` (true / false / null = could not run or a flag), a plain `reason`, and a
`margin` (0 at the threshold, 1 far inside it).

| Check | From | Fails when |
|---|---|---|
| `snr` | pipeline | SNR < 7 |
| `odd_even` | pipeline | alternate dips differ by > 3σ and > 5% |
| `secondary_eclipse` | pipeline | a dip at phase 0.4–0.6 is > 3σ and > 10% of the main dip |
| `size` | pipeline | even the low end of the radius range is > 2 R_Jup |
| `period_alias` | hunt | P/2: a dip half an orbit later is > 50% as deep (> 3σ). 2P / 3P: the dips split into every-2nd / every-3rd groups, and one group is < 50% as deep as the rest (> 3σ) |
| `momentum_dump` | hunt | reaction-wheel desaturations (QUALITY bit 32) or other default-masked cadences fall within half a duration + 30 min of the dips: fails if fewer than 2 dips are clean, the clean dips are < 50% as deep (> 3σ), or > 50% of dips are affected |
| `sector_depth` | hunt | per-sector depths disagree (χ² chance < 0.001 and a spread > 50% of the mean); null with one sector |
| `duration` | hunt | the duration is > 2× or < 0.1× the central-transit duration for the star's density (TIC ρ★, else M★/R★³, else R★ with M = R for dwarfs) |
| `single_sector` | hunt | never fails: flags a signal whose dips all fall in one sector |

Per-dip depths use the local baseline, with errors inflated by the red-noise factor measured at the transit
duration.

## 4. Filter

A signal becomes a candidate only if it passes every stage, in this order (the first stage it fails is
recorded for the funnel):

1. `snr`: SNR ≥ 10
2. `sde`: SDE ≥ 9
3. `transits`: ≥ 3 transits with data
4. `checks`: no check failed, and every must-run check (all except `sector_depth` and `single_sector`)
   actually ran. A star with no TIC radius therefore gives no candidates: size and duration cannot be vetted.
5. `known`: the period does not match a confirmed planet, TOI, CTOI or TESS EB catalogue entry on the same
   star (within 1%, or a ×2, ×3, ½ or ⅓ alias, as in `hunter.known.match_period`). Every TOI disposition counts,
   false positives included.
6. `neighbour`: ... nor a listed star within 2.5′ (≈7 TESS pixels), which would be the likely source of
   the dips.

The lists are downloaded in bulk once a day (the EB catalogue once a month) and matched locally. A sweep
snapshots them once, so every star is checked against the same lists.

## 5. Score (0–100)

```
score = 100 × (0.40·S_snr + 0.20·S_transits + 0.25·S_margin + 0.15·S_bright) × (0.8 if single-sector)

S_snr      = 1 − exp(−(SNR − 10) / 20)     0 at the SNR cut, 0.63 at SNR 30
S_transits = 1 − exp(−(N − 3) / 6)         0 at 3 transits, 0.63 at 9
S_margin   = mean margin of odd_even, secondary_eclipse, size, period_alias, momentum_dump,
             sector_depth, duration
S_bright   = clip((13 − Tmag) / 5, 0, 1)   0 at Tmag 13, 1 at Tmag 8 (easier follow-up)
```

Each candidate stores the terms and weights under `score_detail`.

## 6. Output

`candidates/<tic>_<n>.json` (n = signal number on that star) contains `tic`, `period_d`, `t0_btjd`,
`duration_h`, `depth_ppm`, `snr`, `sde`, `n_transits`, `sectors`, `radius_rjup` `[low, high]` (1σ; also
`radius_rjup_best`, `radius_rearth_best`), `checks` (each with value, pass/fail and reason), `score` +
`score_detail`, `known` (lists checked, matches on the star and on neighbours, other entries on the star),
`curves`, `created_at`. It also holds per-sector depths, transit times, masked known planets, the TIC row
and the data products used.

`curves`: `folded` (200 phase bins over the whole orbit), `folded_zoom` (±3 durations, in hours) and
`unfolded` (30-minute bins over time). A `.png` with all three is written next to each JSON.

`results/<tic>.json` records every star searched, with every signal and the stage it failed at.
`hunt merge` writes `candidates.json` (ranked index + funnel) and `funnel.json`.

## 7. Sensitivity (`hunt inject`)

Box transits are multiplied into the real, un-detrended light curves of quiet stars (their own search has
nothing passing SNR ≥ 10, SDE ≥ 9 and ≥ 3 transits), taken in target order. Then the same search, checks and
cuts are run.

- Grid: radius 1, 2, 3, 4, 6, 8, 11, 15 R⊕ × period 0.5, 1, 2, 4, 7, 10, 15 d (42 bins, cycled so that
  every bin gets the same number of injections).
- Within a bin, radius and period are log-uniform. The impact parameter is uniform in 0–0.7, and the duration
  comes from the star's density.
- **detected:** a returned signal lies within 1% of the injected period and in phase with it.
- **recovered:** detected, and the signal passed every cut and check. This is the number the app shows.
- `sensitivity.json` holds per-bin counts and fractions, marginals by radius and by period, and the star list.
  `sensitivity_injections.jsonl` holds every injection.

## 8. CI

`ci/sweep.yml` is the nightly GitHub Actions workflow (the DEPLOY session installs it): targets + catalogue
snapshot → 20 shards (`fail-fast: false`, 350-minute budget each) → merge → `hunt-candidates` artifact.

## Cache

`~/.cache/planet-hunter/hunt` (override with `HUNT_CACHE_DIR`) holds catalogues (1 day; EB list 30 days), sector
star lists (30 days) and xMatch results (kept). The pipeline's own cache (`HUNTER_CACHE_DIR`) keeps FITS files.

## Tests

`uv run pytest` runs offline on recorded real TESS data in `tests/data/` (made by `tests/data/record.py`):

- **TOI-7303.01** (TIC 415739607, a PC TOI, not confirmed): the signal is found and passes every check. The
  known-list stage rejects it; with empty lists it would have been a candidate. A sibling search masks it
  away.
- **TIC 408512382**, a detached EB in the TESS EB catalogue, is rejected by `secondary_eclipse` (and is on
  the EB list too).
- **TIC 175516858**, a quiet M dwarf: an injected 1.6 R⊕ planet is recovered as a full candidate. Its JSON
  and plot are checked.
- Unit tests on synthetic curves cover each added check, the score formula, catalogue alias and neighbour
  matching, masking, ranking, sharding, and the funnel/merge.

# hunt: planet-hunter PLANET FINDER

A systematic search of TESS light curves for **new planet candidates**, which people then review in the app.
Every sector a star has is stitched together, and the search looks for periodic signals from 0.5 d up to half
the baseline (BLS, plus TLS for small planets) and for long-period planets that show only one or two dips.
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
uv run pytest -m "not deep"                                           # the same without the all-sector proofs
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
- **Ranking** (DEEPHUNT): three priority groups, then HUNT's tiers inside each group.

  | Group | Rule | Why first |
  |---|---|---|
  | 0 deep | observed in ≥ 5 sectors, Tmag ≤ 11, quiet | long baselines catch long periods and single dips; many transits lift small planets above the noise; bright quiet stars reach the smallest |
  | 1 many sectors | observed in ≥ 5 sectors | the same, noisier |
  | 2 few sectors | the rest | HUNT already searched these the way their data allow |

  "Quiet" = a dwarf (class DWARF and log g ≥ 4.0, or no log g), Teff ≤ 6500 K (hotter stars pulsate) and < 10 %
  of the aperture flux from other stars (TIC contamination ratio). There is no photometric-noise number for a
  star before its light curve is downloaded, so these are proxies; brightness sets the photon noise.
  Sector counts come from `coverage.py`: tess-point's pointing and camera tables applied to all stars at once
  (about a second for 730k stars; tess-point's own star-by-star function takes over 10 minutes per 100k).
  On 600 random stars not used to tune it, it matches tess-point exactly for 94.7 %, within one sector for
  99.5 %, and puts 99.0 % on the same side of the 5-sector line. Only sectors up to the newest public one count;
  tess-point 0.9.5's table ends at sector 132.
  On HUNT's 2026-09-25 list (730,692 new-star targets) the groups hold 19,489 / 516,464 / 194,739 stars: 73 % of
  Tmag ≤ 13 stars already have ≥ 5 sectors (median 6), so brightness and quietness do most of the sorting.
- Tiers: tier 0 = M dwarf (Teff < 4000 K, dwarf); tier 1 = small star (R★ < 0.8 R☉, dwarf); tier 2 = other
  dwarfs; tier 3 = giants, subgiants and stars with no class. Within a tier, smaller stars come first
  (deeper dips), then brighter ones. Every row carries a plain `reason` (group, sector count, tier, ...).
- `targets.csv` interleaves B and A (one sibling, one new star, ...) for the sweep.
- `targets_summary.json` has the counts at every step.

## 2. Search (`hunt run`)

Each star runs as its own process: stitch every sector → mask known planets (list B) → periodic search →
checks → known lists → filter → score → single / double dip search on what is left.

**Stitching** (`lightcurve.stitch`). Every sector with a light curve, the best product per sector (SPOC 2-min,
else TESS-SPOC, else QLP FFI; the pipeline's `choose_products`), each normalised by its own median, cadences
with lightkurve's default quality flags dropped. The same FITS files are re-read for the QUALITY column
(momentum dumps, flagged cadences) and SAP_BKG (background, normalised per sector). The curve keeps its native
cadence. The searches work on a copy averaged into 10-min bins per sector (a 42-sector star is 130k points instead
of 630k) and then measure and vet on the native curve: 10-min bins smear transits shorter than an hour (an
injected 52-min transit failed odd/even on binned data and passes on native data). Each star records
`sectors_used`, `baseline_d` and `cadence_mix`.

**Detrending** (`detrend.py`): wotan's time-windowed biweight, split at gaps > 0.5 d, with found and known
transits left out of the trend. The window is 3× the longest duration each search looks for: 0.9 d for the
short-period BLS (HUNT's), 3× the longest duration of the long-period grid for the long BLS and TLS (3 d for most
stars, never less than 0.9 d), and 0.5 / 1.5 / 3 d for the dip search's 1–4 h / 6–12 h / 16–24 h tiers.

**Periodic search** (`deep.py`, `signals.py`), up to 3 signals per star, each with the previous ones masked:

| Search | Periods | How |
|---|---|---|
| `bls_short` | 0.5–15 d | the pipeline's two-pass BLS, unchanged |
| `bls_long` | 15 d – half the baseline | astropy BLS on a frequency grid whose step lets a transit of half the central-transit duration drift at most a third of that over the baseline (the Ofir 2014 / TLS convention); factor-2 period blocks, each with durations from 0.35× the central duration for 3× the star's density up to 1.5× it for ⅓ (1–24 h), its own bin width, and astropy phase bins of a third of the shortest duration. Blocks run in increasing period within a 180-s budget per round; the longest period reached is recorded (`bls_long_pmax_d`, `bls_long_stopped_by_budget`) |
| `tls` | 0.5 d – half the baseline | transitleastsquares (limb-darkened template, better than a box for small planets), single-threaded. Its cost (points × periods) is predicted first; if the whole curve would take over 60 s, TLS runs on the newest sectors that fit and the BLS searches still cover everything. What it ran on is recorded per star (`search.periodic.runtime.tls_runs`) |

Each find is re-measured on the native curve (depth, odd/even depths, epochs with data, the pipeline's
red-noise SNR; depth errors scaled by the red-noise factor at the transit duration), and the one with the highest
SNR is kept. `found_by` lists every search that found the same period. Another round follows while the last
signal had SNR ≥ 7 and SDE ≥ 7 (a low-SDE bump from the long search is not worth masking). "Periodic" still
needs ≥ 3 transits with data, and the new `three_dips` check makes sure three dips are real.

- **Known hosts (list B):** every listed signal on the star with an ephemeris is masked before searching.
  That covers confirmed planets, TOIs, CTOIs and the EB catalogue, and each list's entry is used, because a
  TOI often has a newer ephemeris than the confirmed-planet row. Masked points leave both the trend and the
  search. Three layers:
  1. **Fixed:** ±(1 listed duration + 3σ of the propagated timing error + 2% of P when the archive flags
     TTVs) around every predicted mid-time. It is skipped if the timing allowance is over 0.5 d.
  2. **Observed times:** near each predicted mid-time (within that allowance, at least 1.5 durations, at
     most 0.3 P) the deepest dip of the listed duration is located. If it is ≥ 5σ, it is masked ±1 duration
     around where it actually is. This follows TTVs and drifted or rounded periods; each masked planet
     reports `transits_located` and `median_offset_h`.
  3. **Leak check:** if the search still returns a signal (SNR ≥ 7) at a period listed for this star, it is
     the known planet leaking through. It is masked at the period and epoch the search found, and the
     search is repeated (up to 3 rounds).

  Why: in the first sweep, TOI-1130 c came through. It has strong TTVs, and its transits in S67–S104 fall
  3.8 h from the confirmed ephemeris. TOI-181 b came through too: its confirmed period is rounded to 4.532 d
  with a 2e-6 d error bar. In both cases the old code also dropped the TOI entry that had the better
  ephemeris. Both cases are now tests.
- `--shard i/N` (0-based) takes rows i, i+N, i+2N, ... of the ranked file, so every shard gets top-priority
  stars. The run is resumable: stars already in `results/` are skipped.
- `--time-budget-min M`: a new star starts only if it can plausibly finish before the deadline. A star is
  killed after 15 minutes (MAST sometimes stops answering mid-read; a 40-sector star needs several minutes) and
  recorded as `timeout`.

## 3. Checks

Every check has `value`, `passed` (true / false / null = could not run or a flag), a plain `reason`, and a
`margin` (0 at the threshold, 1 far inside it).

| Check | From | Fails when |
|---|---|---|
| `snr` | pipeline | SNR < 7 |
| `odd_even` | pipeline | alternate dips differ by > 3σ and > 5%. DEEPHUNT widens the errors by the scatter *within* the odd and within the even dips (depths that change from sector to sector, e.g. with crowding corrections, are not an odd/even difference; an EB's alternation is between the groups and untouched) |
| `secondary_eclipse` | pipeline | a dip at phase 0.4–0.6 is > 3σ and > 10% of the main dip |
| `size` | pipeline | even the low end of the radius range is > 2 R_Jup |
| `period_alias` | hunt | P/2: a dip half an orbit later is > 50% as deep (> 3σ). 2P / 3P: the dips split into every-2nd / every-3rd groups, and one group is < 50% as deep as the rest (> 3σ) |
| `momentum_dump` | hunt | reaction-wheel desaturations (QUALITY bit 32) or other default-masked cadences fall within half a duration (at most 1 h) + 30 min of mid-transit: fails if fewer than 2 dips are clean, the clean dips are < 50% as deep (> 3σ), or > 50% of dips are affected. The 1-h cap is DEEPHUNT's: a day-long transit nearly always contains a dump somewhere |
| `sector_depth` | hunt | per-sector depths disagree (χ² chance < 0.001 and a spread > 50% of the mean); null with one sector |
| `duration` | hunt | the duration is > 2× or < 0.1× the central-transit duration for the star's density (TIC ρ★, else M★/R★³, else R★ with M = R for dwarfs) |
| `three_dips` | DEEPHUNT | leave the strongest dip out: the rest keep < 50 % of the depth or are < 3σ (one dip, a single transit or a glitch, carrying a fold of empty epochs; easy to line up at long periods) |
| `single_sector` | hunt | never fails: flags a signal whose dips all fall in one sector |

Per-dip depths use the local baseline, with errors inflated by the red-noise factor measured at the transit
duration.

## 3b. Single and double dips (`singles.py`)

After known planets and the real periodic signals on the star (SNR ≥ 7 and `three_dips` passed) are masked,
a box matched filter looks for individual dips of 1, 1.5, 2, 3, 4, 6, 8, 12, 16 and 24 h, in three tiers each
detrended with a window 3× its longest duration. For each box

```
SES = (1 − mean flux in the box) / (σ_local · β_sector / √(points in the box))
```

σ_local is the robust scatter of the flattened flux in the surrounding day (scattered light raises it locally),
β_sector the red-noise factor at that duration in that sector. A box needs ≥ 75 % of its cadences. Peaks at
least their durations apart are events (SES ≥ 7, at most 20 per star). Each is refined by a trapezoid fit
(mid-time, depth, T14, ingress) on a local re-detrend with the dip left out of the trend, errors scaled by red
noise. (On TOI-2180 b the box alone put mid-times up to 0.1 d off; the refined times agree with a separate trapezoid fit to 0.002 d.)

**Per-dip rejections** (each a check with a reason):

| Check | Fails when |
|---|---|
| `edge` | the dip (ingress to egress) is within 0.5 d of a sector edge or of a data gap > 0.25 d |
| `momentum_dump` | a dump falls in the dip and without the hour around it the dip keeps < 50 % of its depth (> 3σ) or too little of the dip is left to tell; or > 20 % of the dip's cadences are quality-flagged |
| `shape` | the two halves of the dip differ by > 3σ and > 30 % of the depth (a ramp), or the flux level before and after differs by > 3σ and > 50 % of the depth (a step); measured on the dip-masked local re-detrend |
| `background` | SAP_BKG during the dip is > 3σ and > 1 unit of its own scatter above its surroundings (scattered light, a passing asteroid, a glint) |
| `neighbour_dips` | at merge: 2 or more other stars within 1°, searched in the same sector, have a dip within a quarter of the duration (≥ 1 h) with a duration within ×2. One star can be chance; two is a spacecraft or sky artefact |

**Single** (`kind: "single"`): a clean dip with no partner. Its period comes from Kepler's third law with the
star's TIC density, in a Monte Carlo: log-uniform period prior; impact parameter uniform 0–0.9; eccentricity
Beta(0.867, 3.03) (Kipping 2013) with uniform argument of periastron; density with 25 % error (50 % if derived
from M = R); duration error 20 % (log). Samples are weighted by the chance of transiting (∝ R★/a·(1+e sin ω)/(1−e²))
and of a transit landing in the data (∝ 1/P). Periods that would put another transit on data covering ≥ 50 % of
it are removed. `period_range_d` is the 5–95 % range; `period_range_detail` has the median, the circular
central-transit period, how much of the prior mass the data removed and how much eccentricity the fit needs.
Checks that need a period or several dips (`odd_even`, `secondary_eclipse`, `period_alias`, `sector_depth`) are
reported as **could not run**, never as passed. `size` runs. `duration` fails if even a central transit on a
circular orbit would need > 10,000 d (a 20-h dip on an M dwarf: a bigger, background star is being eclipsed), or
if every period the duration allows would have shown another transit.

**Duo** (`kind: "duo"`): two clean dips in different sectors, each SES ≥ 7, depths within 3σ or ×1.5 and durations
within ×1.6. Allowed periods are P = gap/n (P ≥ 1 d). At every other transit an alias predicts, where the data
cover ≥ 50 % of it, the deepest box within the timing tolerance (3σ of the predicted time + 1 h) is measured;
the alias is dropped if that is < half the dip depth and > 3σ shallower, and a dip of the right depth there
counts as an extra dip. Surviving aliases (`period_aliases_d`) get posterior weights from the same
duration/density model; `period_d` is the most probable. `depth_consistency` compares the two dips; `duration`
passes if at least one surviving alias can give the duration; `aliases` fails if none survive.

**Filter**: `snr` (single SES ≥ 10; duo combined ≥ 10 with each ≥ 7) → `checks` (no failure, every must-run
check ran: `snr`, `size`, `duration`, `edge`, `momentum_dump`, `shape`, `background`; duo also
`depth_consistency`, `aliases`) → `known` / `neighbour` (a listed signal on the star or a neighbour within 2.5′
predicts a transit or eclipse at a dip time, or a duo alias matches a listed period) → `neighbour_dips` (merge).
Every clean dip with SES ≥ 7 gets a record, so the funnel shows what any threshold would let through.

## 4. Filter

A signal becomes a candidate only if it passes every stage, in this order (the first stage it fails is
recorded for the funnel):

1. `snr`: SNR ≥ 10
2. `sde`: SDE ≥ 9
3. `transits`: ≥ 3 transits with data
4. `checks`: no check failed, and every must-run check (all except `sector_depth` and `single_sector`;
   `three_dips` included) actually ran. A star with no TIC radius therefore gives no candidates: size and duration cannot be vetted.
5. `known`: the period does not match a confirmed planet, TOI, CTOI or TESS EB catalogue entry on the same
   star (within 1%, or a ×2, ×3, ½ or ⅓ alias, as in `hunter.known.match_period`). Every TOI disposition counts,
   false positives included.
6. `neighbour`: ... nor a listed star within 2.5′ (≈7 TESS pixels), which would be the likely source of
   the dips.

The lists are downloaded in bulk once a day (the EB catalogue once a month) and matched locally. A sweep
snapshots them once, so every star is checked against the same lists.

## 5. Score (0–1)

One formula for every kind:

```
score = K_kind × (0.40·S_snr + 0.20·S_orbit + 0.25·S_checks + 0.15·S_brightness) × (0.8 if single-sector)

K_kind       periodic 1.0, duo 0.5, single 0.3
S_snr        = 1 − exp(−(SNR − 10) / 20)     0 at the SNR cut, 0.63 at SNR 30 (singles: SES; duos: combined)
S_orbit      periodic: 1 − exp(−(N − 3) / 6) 0 at 3 transits, 0.63 at 9
             duo: 1 / (surviving aliases)   single: 0 (no period)
S_checks     = mean margin of the checks that ran (0 at a check's threshold, 1 far inside it)
S_brightness = clip((13 − Tmag) / 5, 0, 1)   0 at Tmag 13, 1 at Tmag 8 (easier follow-up)
```

A single scores at most 0.24 and a duo at most 0.5, so they sort below every strong periodic candidate: one or
two dips are much weaker evidence than a repeating signal, and a single cannot even be scheduled for follow-up
without its period. `score_parts` = `{snr, transits, checks, brightness}` (`transits` is the S_orbit term); each
is weight × S × K × single-sector factor, so the four parts add up to `score`. `score_detail` keeps the raw terms,
the weights, `kind` and the factors. Periodic scores are HUNT's formula; they move slightly because `three_dips`
is one more check margin.

## 6. Output

`candidates/<tic>_<n>.json` (n = signal number on that star; `s<m>` / `d<m>` for a single / duo) contains
`kind`, `period_range_d`, `period_aliases_d`, `dips`, `sectors_used`, `baseline_d`, `stitch` and `found_by` (all
changes: [SCHEMA_CHANGES.md](SCHEMA_CHANGES.md)), and HUNT's fields: `tic`, `period_d`, `t0_btjd`,
`duration_h`, `depth_ppm`, `snr`, `sde`, `n_transits`, `sectors`, `radius_rjup` `[low, high]` (1σ; the same
numbers as `radius_low`/`radius_high`, plus `radius_rjup_best`, `radius_rearth_best`), `checks` (each with
value, pass/fail and reason), `score` (0–1) + `score_parts` + `score_detail`, `known_lists` (lists checked,
matches on the star and on neighbours, other entries on the star; `status` is `not_on_lists` for every
candidate), `folded`, `folded_zoom`, `unfolded`, `created_at`. It also holds per-sector depths, transit
times, masked known planets, the TIC row and the data products used.

Curves: `folded` (200 phase bins over the whole orbit; null for a single, the most probable alias for a duo),
`folded_zoom` (±3 durations, in hours; singles and duos stack their dips) and `unfolded` (30-minute bins over
time, wider for stitched curves so it stays under 6,000 points; `bin_minutes` says which). Singles and duos also
get `dip_curves`, each dip on its own. A `.png` is written next to each JSON.

`results/<tic>.json` records every star searched, with every signal and dip and the stage each failed at,
its dip `events` (with rejection reasons), the stitching and what each search did and how long it took.
`hunt merge` runs the `neighbour_dips` test, then writes `candidates.json` (ranked index + funnel +
`rejected_at_merge`), `funnel.json` (HUNT's periodic funnel plus `dips.single` / `dips.duo`, with candidates per
1,000 stars) and `summary.json`
(`{funnel, n_candidates, shards}`, which FINDER-API reads). With `--sensitivity`, it also copies
`sensitivity.json` alongside them.

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

`ci/sweep.yml` is the nightly GitHub Actions workflow. The DEPLOY session installs it as
`.github/workflows/sweep.yml`: targets + catalogue snapshot → 20 shards (`fail-fast: false`, shard failures
non-fatal, 350-minute budget each) → merge → artifact.

- Workflow `name: sweep` and artifact `candidates` are what FINDER-API's `finder.yml` expects
  (`workflow_run.workflows: ["sweep"]`, `gh run list --workflow sweep.yml`, `SWEEP_ARTIFACT: candidates`).
- The latest `sensitivity.json` is committed at `hunt/results/sensitivity.json` and shipped in each artifact.
- **It assumes a public repository.** A night uses about 7,100 runner-minutes (20 × ~355 + ~15), roughly
  215,000 a month. That is free and unmetered on a public repo; the private free plan's 2,000 minutes a
  month would run out on the first night.

## Cache

`~/.cache/planet-hunter/hunt` (override with `HUNT_CACHE_DIR`) holds catalogues (1 day; EB list 30 days), sector
star lists (30 days) and xMatch results (kept). The pipeline's own cache (`HUNTER_CACHE_DIR`) keeps FITS files.

## Tests

`uv run pytest` runs offline on recorded real TESS data in `tests/data/` (made by `tests/data/record.py`).
The all-sector proofs are marked `deep` and take several minutes each; `uv run pytest -m "not deep"` skips them.

DEEPHUNT proofs (`tests/test_deep_real.py`; the two stars are stored with every sector, at 10-min bins to keep
the repository small, which does not affect 11- and 24-hour transits):

- **TOI-813 b** (TIC 55525572, found by Planet Hunters TESS volunteers; P = 83.8911 d): recovered from 42
  stitched sectors (2,719-day baseline) by `bls_long` as a periodic candidate; see "Proof results" below.
- **TOI-2180 b** (TIC 298663873; P = 260.79 ± 0.59 d, Dalba et al. 2022, one TESS transit in year 2): the
  single-dip search on the year-2 sectors (14–26) finds the transit and gives a period range containing
  260.79 d. With every sector TESS has since seen two more transits (sectors 48 and 57), and the stitched search
  finds it as periodic from its three dips.
- **False alarms** (TIC 121490076, Tmag 9.0, sector 96, from the calibration sweep; one sector stored): a 3.6-h,
  6,800-ppm dip at BTJD 3927.09 (SNR 13 in the sweep) is rejected by `momentum_dump` ("47% of the dip's cadences
  are quality-flagged; the dip is built around missing or bad data"), and a 1.1-h dip at BTJD 3933.28 (SNR 11)
  by `background` ("the sky background rises during the dip (21.3 sigma ...): scattered light or a passing
  object"), `edge` and `momentum_dump`. A weaker one, TOI-2180's sector-75 dip (0.9 h, SNR 9.2, below the cut
  anyway), sits on a reaction-wheel momentum dump and is rejected by `momentum_dump` too.
- **Known-good periodic** (HUNT's tests, unchanged and passing on the deep search): TOI-7303.01 found and
  filtered as known, the EB rejected by `secondary_eclipse`, the injected 1.6 R⊕ planet recovered as a candidate,
  and the TOI-1130 / TOI-181 sibling masking cases.
- `tests/test_dips.py`: synthetic single and double dips (period range contains the truth; duo keeps the true
  alias and drops those the data rule out), each dip rejection (momentum dump, ramp, background spike, edge),
  the too-long-for-an-M-dwarf duration check, score caps by kind, `three_dips`, the new JSON fields, sector
  counts against tess-point, target groups, and the merge-time `neighbour_dips` rejection.

HUNT's tests (still passing):

- **TOI-7303.01** (TIC 415739607, a PC TOI, not confirmed): the signal is found and passes every check. The
  known-list stage rejects it; with empty lists it would have been a candidate. A sibling search masks it
  away.
- **TIC 408512382**, a detached EB in the TESS EB catalogue, is rejected by `secondary_eclipse` (and is on
  the EB list too).
- **TIC 175516858**, a quiet M dwarf: an injected 1.6 R⊕ planet is recovered as a full candidate. Its JSON
  and plot are checked.
- Unit tests on synthetic curves cover each added check, the score formula, catalogue alias and neighbour
  matching, masking, ranking, sharding, and the funnel/merge.

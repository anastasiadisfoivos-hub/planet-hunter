# Candidate JSON: schema changes (DEEPHUNT)

For session CONNECT (API and web). Every field HUNT wrote is still written, with the same name and meaning,
except where noted as "may now be null". Everything else is added.

## 1. `candidates/<tic>_<n>.json`

### New: `kind` and ids

| Field | Type | Meaning |
|---|---|---|
| `kind` | `"periodic"` \| `"duo"` \| `"single"` | periodic: 3 or more dips at a known period. duo: two dips in different sectors, period is one of a list. single: one dip, period is a range. |
| `id` | string | Unchanged for periodic: `hunt:<tic>:<n>`. Singles and duos: `hunt:<tic>:s<m>` / `hunt:<tic>:d<m>`. File names follow the id: `<tic>_s1.json`, `<tic>_d1.json`. |

### Fields that may now be null

| Field | periodic | duo | single |
|---|---|---|---|
| `period_d` | number | the most probable surviving alias | **null** |
| `sde` | number | **null** (no periodogram) | **null** |
| `folded` | object | folded at the most probable alias | **null** (no orbit to fold on) |

`folded_zoom`, `unfolded`, `t0_btjd`, `duration_h`, `depth_ppm`, `snr`, `n_transits`, `radius_*`, `checks`,
`score`, `score_parts` and the rest are always present. For singles/duos: `t0_btjd` is the first dip's
mid-time, `snr` the dip's single-event SNR (duo: both combined in quadrature), and `n_transits` the number of
dips (1 or 2).

### New fields (all kinds)

| Field | Type | Meaning |
|---|---|---|
| `period_range_d` | `[low, high]` or null | single: 5-95% range from duration and stellar density (null if the TIC has no radius). duo: shortest and longest surviving alias. periodic: null (the period is measured). |
| `period_range_detail` | object | singles/duos only: `method`, `percentiles`, `median_d`, `circular_central_period_d`, `mass_excluded_by_data`, `shortest_period_allowed_by_data_d`, `eccentricity_median`, `fraction_needing_e_above_0.5` (whichever apply). |
| `period_aliases_d` | list of numbers or null | duo: every surviving period gap/n, most probable first. Otherwise null. |
| `period_aliases` | list or null | duo: the same with `n`, `weight` (posterior probability, sums to 1), `duration_fit`, `extra_dips` (further dips found where that alias predicts one). |
| `dips` | list | one entry per dip. periodic: `mid_btjd`, `depth_ppm`, `depth_err_ppm`, `duration_h`. single/duo: also `mid_err_d`, `duration_err_h`, `ingress_h`, `snr`, `sector`, `coverage`, `shape_fit` (`"trapezoid"` or `"box"`). |
| `sectors_used` | list of ints | every sector stitched for this star (`sectors` keeps its old meaning: the same list). |
| `baseline_d` | number | first to last data point, days. |
| `stitch` | object | `sectors_used`, `n_sectors`, `baseline_d`, `cadence_mix` (e.g. `{"SPOC 120 s": [..], "QLP 600 s": [..]}`), `bin_minutes`, `n_points`, `days_with_data`, `background_read`. |
| `found_by` | list | which searches found this period: `bls_short`, `bls_long`, `tls`, or `dip_search`. |
| `search` | object | `kept` (the search whose result was kept), `found_by`, `each_search` (period/SNR/SDE per search). |
| `dip_curves` | list | singles/duos: each dip's own zoom (`mid_btjd`, `hours_from_mid`, `flux`). |

### Checks

- Periodic candidates get one more check, `three_dips` (leave the strongest dip out; the rest must keep half the
  depth at 3 sigma). It is a must-run check.
- Singles and duos carry: `snr`, `size`, `duration`, `edge`, `momentum_dump`, `shape`, `background`,
  `depth_consistency` and `aliases` (duo), and `neighbour_dips` (added at merge). Checks that cannot run on one
  or two dips (`odd_even`, `secondary_eclipse`, `period_alias`, `sector_depth`; `depth_consistency` and `aliases`
  for a single) are present with `passed: null` and a reason starting "Could not run:". They are **not** passes;
  the web should show them as "couldn't run", not as ticks.
- A check object may carry a `matches` list (`neighbour_dips` only).

### Score

`score` stays on 0-1 and `score_parts` keeps its four keys (`snr`, `transits`, `checks`, `brightness`), which
still add up to `score`. New formula for every kind:

```
score = K_kind * (0.40*S_snr + 0.20*S_orbit + 0.25*S_checks + 0.15*S_brightness)
K_kind: periodic 1.0 (x0.8 if single-sector), duo 0.5, single 0.3
S_orbit ("transits" part): periodic 1 - exp(-(N-3)/6); duo 1/(surviving aliases); single 0
```

A single scores at most 0.24 and a duo at most 0.5. `score_detail` adds `kind` and `kind_factor`.
Periodic scores change slightly from HUNT's because `S_checks` now also averages the `three_dips` margin.

### Plots

The `.png` for a single shows each dip on its own in the middle panel (no fold) and says "single, P ~ a-b d";
a duo's is folded at its most probable alias and lists the aliases.

## 2. `results/<tic>.json` (per star)

Added: `dips` (every single/duo examined, compact, with `kind`, `mid_times_btjd`, `period_d`,
`period_range_d`, `n_aliases`, `failed_stage`, `failed_checks`, `score`), `events` (every dip with SNR >= 7:
`mid_btjd`, `duration_h`, `depth_ppm`, `snr`, `sector`, `failed_checks`, ...; the merge compares these across
nearby stars), `stitch`, `search` (BLS/TLS runtimes, what TLS ran on, detrending windows). `signals[]` entries
gain `kind`, `found_by`, `kept`. `timings_s` has new keys (`periodic`, `vetting`, `dips`, `bls_short_s`,
`bls_long_s`, `tls_s`, ...).

## 3. `candidates.json`, `funnel.json`, `summary.json`

- `candidates.json` index rows gain `kind`, `period_range_d`, `period_aliases_d`, `sectors_used`, `baseline_d`;
  `period_d` and `sde` may be null. New top-level `rejected_at_merge` (`{"<tic>:<s1|d1>": reason}`).
- `funnel` keeps every HUNT key. `candidates` now counts all kinds; `periodic_candidates` is HUNT's old
  number. Added: `dips` (`single` and `duo`, each with `found`, `after_<stage>` for `snr`, `checks`, `known`,
  `neighbour`, `neighbour_dips`, `candidates`, `candidates_per_1000_stars`, `check_failures`), `dip_events`,
  `dip_must_run_checks`, `sectors_per_star`.

## 4. `sensitivity.json`

HUNT's keys are unchanged and still describe the 0.5-15 d grid (`grid`, `n_injections`,
`overall_recovery_fraction`, `bins`, `by_radius`, `by_period`, `n_stars`, `stars`, `skipped_stars`,
`definition`). Added: `long_period` and `single_transit`, each with `n_injections`,
`overall_recovery_fraction`, `bins` (each bin also has `recovered_as` = counts by kind), `by_radius`,
`by_period`, `grid`, `recovered_as`; `single_transit` also has `period_in_range_fraction`. Also
`n_injections_all_grids`, and `stars[]` entries gain `n_sectors` and `baseline_d`.

## 5. Targets CSV

Two new columns, `group` (0 deep, 1 many sectors, 2 few sectors) and `n_sectors`; `reason` now starts with the
group. `targets_summary.json` adds `list_a_by_group`, `list_b_by_group` and `sector_counts_up_to`.

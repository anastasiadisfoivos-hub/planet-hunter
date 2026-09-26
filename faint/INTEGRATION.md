# Using skyfaint from DEEPHUNT's search

This page covers what DEEPHUNT (the `hunt` package on the `deephunt` branch) calls to search the faint-star list,
the shapes it gets back, and what a night costs. Every number here was measured on 2026-09-26 and comes from a
file in `faint/results/`.

## 1. Install

`skyfaint` is its own package under `faint/`. To use it from hunt, add it as a path dependency next to the pipeline:

```toml
# hunt/pyproject.toml
dependencies = [..., "skyfaint"]
[tool.uv.sources]
skyfaint = { path = "../faint", editable = true }
```

`skyfaint` does not import hunt at runtime. Only `FaintLC.to_hunt()` imports `hunt.lightcurve.StarLC`, and it does
so inside the method.

## 2. The three calls

```python
from skyfaint import targets, tglc, noise

rows = targets.read("targets/targets_faint.csv.gz")      # list[dict], ranked; one row per star
lc   = tglc.get_lightcurves(int(row["tic"]))              # FaintLC: every TGLC sector, stitched
slc  = lc.to_hunt()                                       # hunt.lightcurve.StarLC, the same arrays (no copy)
n    = noise.star_noise(lc, row)                          # CDPP 1 h / 2 h, smallest detectable radius
```

### Target rows (`targets_faint.csv.gz`, `targets_faint_top.csv`)

The columns are a superset of hunt's `Star` fields, so `hunt.stars.Star.from_row(row)` works on a row as it
stands. `sweep._star_from_row` already takes that path, because rows have `ra` and `tmag`.

| column | meaning |
|---|---|
| `rank`, `tier` | 1-based rank. Tier is 1, 2 or 3 (see README §1) |
| `tic`, `ra`, `dec`, `tmag`, `teff`, `logg`, `rad`, `rad_err`, `mass`, `rho`, `lumclass`, `contratio` | TIC 8.2, the same names as `hunt.stars.Star` |
| `gaia_dr2` | TIC's Gaia DR2 id |
| `n_sectors`, `sectors` | predicted TGLC sectors (1–55), space-separated |
| `pred_cdpp_1h_ppm`, `pred_rmin_p{1,5,10}_rearth` | predicted noise and smallest planet at SNR 10 (from the Tmag model) |
| `reason` | a plain sentence |

The list has no `list` column. Treat every row as list `"A"` (new-star search): known hosts are excluded, so there
is nothing to mask.

### `tglc.get_lightcurves(tic, flux="aper", sectors=None, refresh=False, max_bkg_z=None) -> FaintLC`

It returns the same fields, names, dtypes and conventions as DEEPHUNT's `hunt.lightcurve.StarLC`:

| field | shape / type | content |
|---|---|---|
| `time` | `(n,) float64` | BTJD (BJD − 2457000, TDB), sorted |
| `flux` | `(n,) float64` | normalised to median 1 **per sector** |
| `flux_err` | `(n,) float64` | per-sector constant (TGLC `CAPE_ERR` / median) |
| `sector` | `(n,) int` | sector of each point |
| `products` | `list[dict]`, one per sector | `sector`, `author="TGLC"`, `exptime` (1800 s in S1–26, 600 s in S27–55), `camera`, `ccd`, `filename`, `flux_column`, `flux_note`, `n_good`, `n_total`, `n_scattered_light`, `tessmag_tglc`, `gaia_dr3`, `near_edge` |
| `dumps` | `(k,) float64` | BTJD of momentum-dump cadences (removed from `time`) |
| `flagged` | `(m,) float64` | BTJD of other removed cadences |
| `quality_read` | `bool` | always True (the quality columns are in the file) |
| `bkg` | `(n,) float64` | TGLC background per point, `(b − median) / robust σ` per sector, which is what `singles.check_background` expects |
| `bin_minutes` | `None` | native cadence |
| `meta` | `dict` | `tic`, `gaia_dr3`, `sectors_predicted`, `sectors_published`, `download` (files, bytes, seconds) |

`to_hunt()` builds a `hunt.lightcurve.StarLC` with every field that the installed hunt's `StarLC` has. On hunt it
drops `bkg` and `bin_minutes`; on DEEPHUNT it keeps them. The arrays are shared, not copied.

The call raises `LookupError` when the star has no usable TGLC file. `sweep.process_star` already records that
case as `no_data`.

## 3. Wiring it into `sweep.process_star`

The only change is where the light curve comes from:

```python
# hunt/src/hunt/sweep.py, process_star()
if row.get("source") == "tglc":            # or: a --tglc flag on `hunt run`
    from skyfaint.tglc import get_lightcurves
    lc = get_lightcurves(tic).to_hunt()
else:
    lc = lightcurve.stitch(tic, max_sectors=max_sectors)
res = analyse(star, lc, _CATALOGUE, kind)   # unchanged: deep_search=True, dip_search=True
```

Things DEEPHUNT should know:

- **Cadence.** TGLC is 30-min in S1–26 and 10-min in S27–55. `bin_lc(…, 10)` leaves both as they are. Transits
  shorter than about 1 h are smeared in the 30-min sectors.
- **Already detrended.** TGLC's `cal_aper_flux` has been divided by a 1-day wotan biweight. Re-detrending with
  DEEPHUNT's windows is harmless for P ≲ 15 d. Transits longer than ~5 h, and the long-period search, lose some depth.
- **Scattered light.** Faint-star TGLC curves have dips of several percent where the background rises fast (TOI-1680,
  S52: −9% for hours). No cut is applied by default (README §2 explains why). Use `bkg`: `singles.check_background`
  vetoes those dips. With the stitched deep search, `bls_long` picked such an event as its top signal on TOI-1680
  (README §4), so a background veto for periodic signals would help too.
- **Coverage ends at sector 55** (2022-09). There are no TGLC files for S56 and later.
- **The TOI-1680 lesson.** A 1.5 R⊕ planet at SNR 24 over 24 sectors was missed by hunt's per-sector coarse BLS.
  DEEPHUNT's stitched search also missed it, because long-period artifacts took all its signal slots. See README §4.
  Faint stars with many sectors are exactly where the coherent search matters.

## 4. Nightly throughput

Measured on 54 random faint M dwarfs from the target selection, each with an empty cache (`results/noise_sample.json`):

| per star | median | 90th percentile |
|---|---|---|
| TGLC sectors | 2 | – |
| download size | **193 KB** (95 KB per sector) | 434 KB |
| time, cold (TIC row + Gaia DR3 id + HEAD checks + downloads + read) | **6.7 s** | 11.2 s |
|   of which resolving the files | 4.7 s | – |
|   of which downloading | 1.8 s | – |
| time, warm cache (read + stitch) | 0.02–0.14 s | – |

- 6 of 60 sampled stars had no TGLC file, all at TIC Tmag 15.75–15.99, TGLC's T = 16 limit. Those cost one resolve
  (about 5 s) and raise `LookupError`.
- A long-baseline star costs more. TOI-1680 (24 sectors) is 2.2 MB and 13 s cold.
- Search time dominates. hunt's BLS (origin/hunt) takes 25 s for 7 sectors and 75 s for 24. DEEPHUNT's deep search
  (BLS short + long + TLS, origin/deephunt 30bbe36) takes 74 s for 5 sectors (TIC 219223283), 140 s for 7
  (TOI-5688) and 640 s for 24 (TOI-1680). All timings are on an Apple-silicon laptop, one process. The quiet star's
  only deep-search signal was a two-event, 121-day artifact (SNR 17.6, SDE 2.3), another sign that TGLC's
  scattered-light dips reach `bls_long`.

**A night.** The estimate below assumes about 75 s of deep search per typical faint star (measured at 5 sectors;
the median listed star has 2 or 3) plus 6.7 s of fetching:

- 20 shards × 350 min / 82 s ≈ **5,100 stars a night**;
- about **1.0 GB** of TGLC files (5,100 × 193 KB);
- fetching is about 8% of shard time.

Stars with many sectors (tier 1 needs ≥ 3; CVZ stars have 20+) take several minutes each, so the first nights, which
work down tier 1, will cover fewer stars.

Per-shard caching:

- Keep `FAINT_CACHE_DIR` (default `~/.cache/planet-hunter/faint`) between nights with `actions/cache`. TGLC files never
  change, so a re-searched star costs no downloads.
- The per-star file index is cached for 90 days, and Gaia ids forever.
- The TIC strips, about 0.7 GB of JSON, are only needed to rebuild the target list. Build that once and commit or
  cache the `.csv.gz`.

MAST, the Gaia archive and archive.stsci.edu are free and anonymous. The loader runs up to 8 HEAD/GET requests in
parallel per star, so 20 shards open at most 160 connections at once. No throttling was seen at the sampling rate
used here (one star at a time), and a full 20-shard night has not been tried.

# skyfaint: the faint-star frontier for the Planet Finder

`skyfaint` does two things for small, faint stars: M dwarfs with TESS magnitude 13–16, fainter than the Tmag ≤ 13
cut in `hunt/`.

- It builds a ranked list of these stars.
- It loads their **TGLC** light curves (TESS-Gaia Light Curves, Han & Brandt 2023). TGLC fits TESS full-frame
  images with PSF photometry, using Gaia DR3 to model and remove neighbouring stars, and publishes curves to T = 16
  on MAST.

TESS's own full-frame light curves (TESS-SPOC, QLP) mostly stop around T = 13.5, and `hunt/` stops at 13. An
independent search has its best odds of finding what they missed in this faint range.

It outputs data and targets only. Candidates come from the search in `hunt/` (or DEEPHUNT's version of it). See
[INTEGRATION.md](INTEGRATION.md) for how to call it.

```bash
cd faint && uv sync
uv run skyfaint targets --out targets        # ranked list (first run: ~2-3 h of MAST queries, then cached)
uv run skyfaint lc 259168516                 # every TGLC sector for a star, stitched
uv run skyfaint noise 259168516              # CDPP 1 h / 2 h and smallest detectable planet at P = 1, 5, 10 d
uv run pytest                                # offline, recorded real TGLC data
```

## 1. Targets (`skyfaint targets`)

1. **Selection.** TIC 8.2 via MAST's filtered catalogue service, in 1° declination strips (each cached for good):
   Tmag 13–16, Teff < 4000 K, luminosity class DWARF, object type STAR, not SPLIT/DUPLICATE/ARTIFACT.
2. **Coverage.** The TGLC sectors (1–55) whose cameras contain the star. The footprint uses tess-point's camera
   pointings, vectorised (`coverage.sector_mask`). Against tess-point itself on 1,500 random positions it gives the
   identical sector set for 86% and is within one sector for 97%. It ignores the CCD gaps, so it slightly
   over-counts. The loader re-checks every file.
3. **Dropped** (counted in the summary, never listed):
   - on a known list: TOI (any disposition), CTOI, confirmed-planet host, or TESS EB catalogue. The same sources
     hunt uses, downloaded in bulk;
   - no TGLC sector;
   - TIC contamination ratio > 1;
   - no TIC radius.
4. **Tiers:**
   - **1:** R ≤ 0.4 R☉, ≥ 3 TGLC sectors, contamination ≤ 0.1;
   - **2:** R ≤ 0.6 R☉, ≥ 2 sectors, contamination ≤ 0.3;
   - **3:** the rest, plus every star with Tmag > 15.7. TGLC stops at its own Gaia-fitted T = 16, and 6 of the 11
     sampled stars that faint had no file.
5. **Order within a tier:** the predicted smallest planet detectable at SNR 10 at P = 5 d (§3). This combines
   radius, brightness and number of sectors in one number.
6. **`reason`**, in every row, e.g. *"late M dwarf, R 0.21 R_sun, Teff 3231 K, Tmag 13.31; 24 TGLC sectors
   (S14-S55); contamination 0.02 (low); not a TOI, CTOI, confirmed host or known EB; a 1.0 R_earth planet at P = 5 d
   should reach SNR 10 (predicted)"*.

Crowding uses the TIC's contamination ratio: the flux from Gaia DR2 neighbours in a TESS aperture, relative to the
star's own. TGLC removes known Gaia neighbours by PSF fitting, so the cut (> 1) is looser than it would be for
aperture photometry. The residual risk is a neighbour that is itself variable.

Output: `targets_faint.csv.gz` (every listed star), `targets_faint_top.csv` (first 5,000 rows) and
`targets_faint_summary.json`. The committed run is under `results/`:

TARGET_TABLE

## 2. Light curves (`tglc.get_lightcurves(tic)`)

- **Finding the files.** Sectors 1–11 are in the MAST API; sectors 12–55 exist only as files at predictable URLs
  (s0056 and later return 404). So every sector is found the same way:
  1. The star's Gaia DR3 id comes from the Gaia archive (`dr2_neighbourhood`, from the TIC's DR2 id).
  2. tess-point predicts sector, camera and CCD.
  3. `url_for()` builds the URL and a HEAD request checks it; if that fails, the other CCDs of the same camera are
     tried.
  4. Every downloaded file's `TICID` header must match the star.
- **Flux.** `cal_aper_flux` by default (`flux="psf"` for `cal_psf_flux`). This is TGLC's decontaminated, calibrated
  flux, already divided by a 1-day biweight. It is normalised to median 1 per sector. If the calibrated column is
  broken (TGLC's documented primary-mission problem for very faint stars near variables), the raw flux / median is
  used, and the product says so.
- **Quality.** Cadences are dropped when `TESS_flags & 17087` is set (lightkurve's default bitmask, as hunt uses),
  when `TGLC_flags ≠ 0`, or when the flux is non-finite or ≤ 0. The times of momentum dumps and other dropped
  cadences are kept in `dumps` / `flagged` for hunt's `momentum_dump` check.
- **Scattered light: no cut by default.** Faint TGLC curves dip by several percent where the background rises fast
  (TOI-1680 S52: −9% for hours). A cut at background > 3 robust σ (`max_bkg_z=3`) removes 3–11% of cadences and
  about half of the > 4σ low points. It stays off because it creates new artifacts. It leaves each event's
  shoulders beside a fresh gap, where detrending cannot follow them. On TOI-5688, S51's strongest false peak became
  2.7× stronger, and hunt's SDE for the real planet fell from 10.1 to 5.6. The background is returned in `bkg`
  instead, for searches to veto dips with.
- **Caching.** FITS files are kept for good under `~/.cache/planet-hunter/faint/tglc/` (`FAINT_CACHE_DIR`). The
  per-star index is kept for 90 days.

The returned `FaintLC` has hunt's `StarLC` fields and conventions (time BTJD, per-sector-normalised flux, `sector`,
`products`, `dumps`, `flagged`, `bkg`), and `.to_hunt()` returns a real `hunt.lightcurve.StarLC`. The shapes are in
INTEGRATION.md.

## 3. Noise (`noise.star_noise`)

- **CDPP at 1 h and 2 h, per sector.**
  1. Divide by a 1-day running median and clip at 5σ.
  2. Take the robust scatter (1.4826 × MAD) of the running means over 1 h and 2 h.
  3. Combine the sectors as 1/√mean(1/CDPP²).

  Taking the scatter of the window means keeps red noise in.
- **Smallest detectable planet at SNR 10, for P = 1, 5 and 10 d:**
  - T = the central-transit duration for the star's density;
  - σ(T) = CDPP_1h · (T/1 h)^α, with α from the measured CDPP_2h/CDPP_1h;
  - N = days with data / P;
  - depth = 10 σ(T)/√N;
  - Rp = R★ √depth.

  This is the box SNR that hunt's search reports. It assumes a central transit and no limb darkening, so real
  planets need slightly more.
- **Tmag noise model** (for ranking before any download): log₁₀ CDPP_1h = 3.582 + 0.315 (T−14) + 0.050 (T−14)².
  It is fitted to 54 random faint M dwarfs, with 0.144 dex scatter (`scripts/fit_noise.py`,
  `results/noise_sample.json`). Median CDPP_1h is 2,668 ppm at Tmag 13–14, 5,801 at 14–15 and 14,128 at 15–16.
  Median α = −0.47 (white noise is −0.5). The median is 22.5 days with data per sector.

| star | Tmag | R★ | sectors | CDPP 1 h / 2 h (ppm) | smallest planet at P = 1 / 5 / 10 d (R⊕) |
|---|---|---|---|---|---|
| TOI-1680 (TIC 259168516) | 13.31 | 0.21 | 24 | 1,953 / 1,436 | 0.73 / 0.97 / 1.10 |
| TOI-5688 A (TIC 193634953) | 14.21 | 0.58 | 7 | 4,787 / 3,785 | 3.63 / 4.96 / 5.67 |
| TIC 219223283 (quiet) | 14.82 | 0.59 | 5 | 6,820 / 4,884 | 4.87 / 6.39 / 7.19 |

Late M dwarfs observed in many sectors are where Earth-sized planets come within reach.

## 4. Proof (offline tests on recorded real data)

`tests/data/` holds three stitched TGLC curves and one raw TGLC file, made by `tests/data/record.py`. The searches
are hunt's own `hunt.signals.find_signals` from `origin/hunt`, imported read-only. The two planets were chosen
before any search was run: faint M-dwarf hosts (Tmag > 13), one giant, one small.

| | TOI-5688 A b | TOI-1680 b |
|---|---|---|
| why | fainter host (Tmag 14.21) with a stellar companion, B: tests the decontamination | small planet (1.47 R⊕) on a late M dwarf, 24 TGLC sectors |
| catalogue | P 2.948155 d, Rp/R★ 0.164 → 26,896 ppm (Reji et al. 2025) | P 4.8026345 d, 4,070 ppm (Ghachoui et al. 2023) |
| hunt's search on TGLC | **P 2.948141 d (−0.0005%)**, depth **27,184 ± 512 ppm** (+1.1%), SNR 46.0, SDE 10.1, 57 transits | **not found**: top signal P 13.65 d, SDE 4.2 |
| result | **recovered** | **missed**, cause below |

**TOI-5688 A b, the depth.** The ExoFOP TOI depth, 24,090 ppm, is 11% shallower than the TGLC depth. The published
radius ratio agrees with TGLC to 1%. That is what decontamination should do: TGLC takes the companion's light out of
the aperture, so the transit is not diluted.

**TOI-1680 b, why it was missed.** This is diagnosed, not tuned; `test_toi1680_in_data_but_missed_by_hunt` pins it.

1. **The transit is in the TGLC data.** At the catalogue ephemeris the flux is 4,643 ppm low (catalogue: 4,070) over
   384 in-transit points, SNR 23.7. The noise model predicted SNR ~22.
2. **A phase-coherent BLS finds it.** On the same stitched curve, a BLS over 3–7 d finds P = 4.80263 d, SDE 18.1.
3. **hunt's search cannot.** Its coarse stage runs BLS on each sector separately and adds up the powers, which
   ignores phase. Each of the 24 sectors holds the transit at SNR ≈ 24/√24 ≈ 5. That is below each sector's own
   noise peaks, so the summed power at 4.8 d is at noise level (z = 0.9), and the fine stage never looks there. With
   hunt's default of the newest 3 sectors, the coherent SNR would only be ~8 anyway.
4. **DEEPHUNT's stitched deep search** (`origin/deephunt` at 30bbe36, run read-only) also missed it, for a different
   reason. Its `bls_long` stage took all three signal slots with long-period single events: the TGLC scattered-light
   dips (§2), up to 6.7% deep. The same curve with the 3σ background cut: still a long-period artifact.
   TOI-5688 A b was recovered by the deep search too (P 2.94815 d, SDE 26.1, found by BLS and TLS).

The lesson for the faint frontier: long-baseline faint stars need a phase-coherent search, and a background veto
applied to periodic signals as well as to single dips.

**A faint star with no known planet.** TIC 219223283 was chosen by a fixed rule: the first star of the random noise
sample with Tmag 14–15 and ≥ 3 sectors.

- **Search:** hunt's best signal is P 12.17 d, SNR 4.9, SDE 4.4. Nothing passes SNR ≥ 10, SDE ≥ 9 and ≥ 3
  transits.
- **Noise:** measured CDPP_1h 6,820 ppm against 7,485 predicted by the Tmag model (−0.04 dex, well inside its
  0.144 dex scatter).

`results/proof.json` has every number above (`scripts/proof.py`).

## Tests

`uv run pytest`: 16 tests, offline, about 2.5 min (hunt's BLS on the 24-sector curve is most of that).

- **Reader:** quality flags removed and listed, normalisation, TICID guard, the scattered-light cut.
- **Hunt shape:** `to_hunt()` gives a real `StarLC`.
- **Noise:** CDPP on white and red synthetic noise at 10- and 30-min cadence; the detectable-radius formula.
- **Targets:** tiers, reasons, and the fast footprint against tess-point.
- **Proofs:** the recoveries and the quiet star above.

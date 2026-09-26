# skypixels — is the dip on the target? (planet-hunter `pixels/`)

TESS pixels are 21″ wide, so a planet-like dip in a star's light curve can really be an eclipsing binary a
few pixels away whose light leaks into the aperture. This is the #1 false-positive check: **difference imaging**.
It finds where on the sky the light went missing during transit, then compares that spot with the target and
with every Gaia DR3 neighbour.

```bash
uv sync
uv run skypixels vet --tic 100100827 --period 0.9414525 --t0 3205.353322 --duration 2.05 --out out/wasp18
# --t0 accepts BTJD or full BJD; --sectors 62 63 to choose sectors (default: newest 3); --refresh re-queries
```

```python
from skypixels import vet_pixels
v = vet_pixels(75208638, period_d=4.6512523, t0_btjd=2990.712909, duration_h=2.251, sectors=None, out_dir="out")
v.verdict, v.reason, v.on_target_probability, v.suspect_neighbours
```

Free services only, no sign-ups: MAST (TIC, SPOC target pixel files, TESScut), the ESA Gaia archive (falls back
to CDS VizieR `I/355/gaiadr3`).

## Method

| Step | Module | What it does |
|---|---|---|
| catalogues | `catalog.py` | TIC 8.2 row; Gaia DR3 within 4′ down to G_target + 10. The target's Gaia source is matched by its DR2 id, else by the nearest source < 3″ whose G agrees within 1 mag. Gaia G, BP−RP → TESS mag (Stassun et al. 2019, eq. 1). |
| pixels | `fetch.py` | Per sector: a SPOC 2-min **target pixel file** if one exists, else a 15×15 **TESScut** FFI cutout. Default: the newest 3 sectors. |
| reduce | `reduce.py` | Quality-flagged frames dropped. For each transit: in-transit frames \|t−tc\| < 0.4 D; out-of-transit windows on **both** sides, 0.75 D to 0.75 D + max(D, 1.2 h). Per-transit difference = ½(before + after) − in-transit (a linear drift cancels). Sector difference image = mean over transits. Its per-pixel variance comes from frame-to-frame noise, scaled up to the transit-to-transit scatter when that is larger (≥ 6 transits). |
| scene fit | `psf.py` | The out-of-transit image is fitted as F_t × (target + Σ catalogue-ratio × neighbour) + background. The PSF is a pixel-integrated elliptical Gaussian, and every star is proper-motion-corrected to the sector epoch and placed with the sector WCS. Free parameters: a common shift (dx, dy), which corrects the WCS, the PSF shape, F_t and the background. |
| centroid | `psf.py`, `analyze.py` | One PSF (the scene's shape) + background fitted to the difference image gives the centroid, its covariance and ΔF, the flux lost. Offset = centroid − calibrated target position, converted to (east, north) arcsec. A sector counts only if ΔF > 0 at SNR ≥ 5. |
| combine | `analyze.py` | Inverse-covariance-weighted mean of the sector offsets (each sector covariance gets a 0.05 px per-axis systematic floor). If sectors disagree (χ²/dof > 1), the error is widened by that factor. **offset_sigma** = √(oᵀC⁻¹o), the Mahalanobis distance. |
| neighbours | `analyze.py` | For every Gaia star within 2.5′, **needed_depth** = depth_on_target × 10^(0.4 (T_nb − T_target)), where depth_on_target = ΔF / F_t. This is the eclipse depth that star would need to produce the dip. A neighbour is **suspect** when needed_depth ≤ 100 % and the centroid does not exclude it. |

**Excluded / off target.** A position is excluded when the centroid is **> 3σ from it and > 0.3 px** away.
The pixel floor stops a very bright star with tiny formal errors from being called off target on PSF-model
systematics.

### Verdict

| verdict | when |
|---|---|
| `inconclusive` | no sector shows the dip in the pixels (difference-image SNR < 5), or there is no pixel data. `depth_upper_limit_3sigma` is given instead. |
| `off target` | the target's position is excluded. The reason names the Gaia neighbour the centroid lands on, if one can host the dip. |
| `possible neighbour` | the target is not excluded, but at least one neighbour that could host the dip is not excluded either (it sits too close to tell apart). |
| `on target` | the target is not excluded, and every neighbour able to host the dip is excluded. |

### on_target_probability (heuristic, not a calibrated probability)

```
P(on target) = L_t / (L_t + Σ_i w_i · L_i + e^(−4.5))
L_s = exp(−½ d_s²),  d_s = Mahalanobis distance of the combined centroid from star s,
      using the combined covariance + (0.1 px)² per axis
i   = Gaia neighbours with needed_depth ≤ 1;  w_i = 0.25 if needed_depth ≤ 0.5, else 0.05
e^(−4.5) = "somewhere else" (an uncatalogued source or systematics), i.e. a fixed 3σ miss
```

A centroid exactly on an isolated target gives 0.99; 3σ off with no neighbour gives 0.5. The target's prior
weight is 1 because the ephemeris came from the target's own light curve. Neighbours are down-weighted because an
eclipse deeper than 50 % is uncommon. The value is `null` when the verdict is `inconclusive`.

## Output

`pixel_vet.json` (the `PixelVet` dataclass) contains:

- `verdict`, `reason`, `on_target_probability`
- `centroid_offset_arcsec`, `centroid_offset_px`, `offset_sigma`, `offset_east_north_arcsec`
- `depth_on_target` ± err, `depth_upper_limit_3sigma`, `tic_contamination_ratio`
- `suspect_neighbours: [{gaia_id, sep_arcsec, gmag, tmag, needed_depth, centroid_distance_sigma}]`
- `neighbours` (every Gaia star ≤ 2.5′), `per_sector`, `heuristic`, `warnings`, `data`, `timings_s`, `files`

Per sector it also writes:

- `tic<id>_s<sector>_pixels.png`: out-of-transit image (log scale) and difference image, with the target, the
  Gaia neighbours (orange = could host the dip), the dip centroid with 1σ/3σ ellipses, the SPOC aperture and
  a N/E compass.
- `tic<id>_s<sector>_pixels.json` (4–45 kB) for the web UI: `out_of_transit`, `difference`,
  `difference_snr` (image[row][col], pixel centres at integers), `markers` (target / neighbour / suspect with
  pixel x, y), `centroid` {x, y, cov_px}, `aperture`, `compass`, `pixel_scale_arcsec`.

## Known limits

- The Gaussian PSF misses TESS's wings, so `depth_on_target` runs ~15 % low. For WASP-18 b it measures 0.98 %
  against 1.14 % in the TOI catalogue. `needed_depth` scales with it, and that is the right precision for
  "could this star plausibly do it".
- The scene fit's WCS shift is anchored mostly by the brightest star. A position error common to the whole field
  is calibrated out, and so, in an otherwise empty field, is a proper-motion error of the target alone. That is
  why proper motions are always applied.
- Saturated targets (T < 6.8) raise a warning: bleed columns make the PSF fit poor.

## Cache

The cache lives in `~/.cache/planet-hunter/pixels` (override with `SKYPIXELS_CACHE_DIR`). FITS files are kept
for good, the product lists for 6 h, and TIC/Gaia answers for 30 days.

## Tests

```bash
uv run pytest                              # offline: synthetic scenes + recorded real TESS data
uv run pytest --run-network -m network     # live MAST/TESScut/Gaia
uv run python scripts/record_fixtures.py   # re-record tests/data/ and reports/ (needs internet)
```

The real-data cases are in `tests/data/cases.json`. The reduced per-sector images and catalogue answers are
recorded under `tests/data/<case>/`, and a raw 8-transit pixel crop of WASP-18 tests the reduction step itself.

| case | expected | source |
|---|---|---|
| WASP-18 b (TIC 100100827) | on target | TOI-185.01, TFOPWG KP |
| TOI-4257.01 (TIC 75208638) | off target, onto TIC 75208617 = Gaia DR3 5423774792624492928 | ExoFOP TOI table: TESS disp. EB, TFOPWG **FP**, comment "offset on TIC 75208617 in SPOC s62; retired as TFOP FP/NEB" |
| TIC 100101861, invented ephemeris | inconclusive | a T = 9.3 star with no TOI/CTOI |

Results and figures from those runs are in `reports/`.

# hunter — TESS science pipeline (planet-hunter `pipeline/`)

Hunts one TESS star for repeating dips (transits / eclipses) and flares and returns contract `Discovery`
objects. Types are best guesses with a confidence; nothing here is ever called "discovered" or a "new planet".

```bash
uv sync
uv run python -m hunter WASP-43            # or "TIC 36734222" or 36734222
uv run python -m hunter WASP-18 --max-sectors 4 --out out/
```

Writes `result.json` (target, data used, discoveries, every signal examined with its vetting, timings) and
`tic<id>_sig<n>_folded.png` per signal.

```python
from hunter import hunt, latest_data_marker, StarTarget
discoveries = hunt(StarTarget(36734222))   # list[Discovery]; also accepts a name or a TIC number
latest_data_marker(36734222)               # "sector-100" (MAST product listing only, no downloads)
```

## Steps

| Step | Module | What it does |
|---|---|---|
| resolve | `resolve.py` | name / TIC → TIC 8.2 row (RA, Dec, R★, Teff, Tmag). A missing R★ stays `None`. |
| fetch | `fetch.py` | Best product per sector: SPOC 2-min PDCSAP > TESS-SPOC PDCSAP > QLP. Newest `--max-sectors` (default 2) sectors of the best available kind. |
| clean | `clean.py` | Per-sector normalise; biweight trend (0.9 d window = 3× the longest trial transit), evaluated per data segment. Transit search clips **upward** outliers only. |
| search | `search.py` | astropy BLS, P 0.5–15 d, duration 0.03–0.3 d. Coarse per-sector search (likelihood powers summed), then a fine search on all data. First pass → mask transits → re-flatten → search again. Up to 3 signals. |
| measure | `measure.py` | Rp = R★ · √depth. |
| vet | `vet.py` | odd/even depths; secondary dip at phase 0.4–0.6; radius > 2 R_Jup; SNR < 7. Each is pass/fail (or `None` = could not run) plus a plain-English reason. |
| flares | `flares.py` | Unclipped curve, 0.25 d trend, ≥3 points > 3σ, peak > 5σ, fade ≥ 2× rise, eclipses masked out. |
| known | `known.py` | NASA Exoplanet Archive confirmed planets, TOI table, ExoFOP CTOIs (+ TESS EB catalogue, Prša+ 2022, for eclipsing binaries). Period within 1% or a ×2, ×3, ½, ⅓ alias. |

## Classification

- SNR < 7 → no transit Discovery (still listed under `signals_examined` in `result.json`).
- Odd/even mismatch or a big secondary dip → `eclipsing_binary`, confidence 0.6–0.95.
- Only the size test fails → `eclipsing_binary`, confidence 0.3, "too large to be a planet; could be a small
  star or a blended signal".
- Everything passes → `planet_candidate`, confidence 0.5–0.9 by SNR (−0.15 when R★ is unknown).

## Contract choices (agreed)

- `light_curve` = `{"time_btjd": [...], "flux": [...]}`: flattened, binned to ≤2000 points, not folded. For
  flares it is the unbinned ±0.2 d window around the peak.
- `detected_at` = first transit mid-time in the data (or flare peak), BTJD → ISO-UTC.
- `id` = `tess:<tic>:sig:<n>` (n = 1 strongest) and `tess:<tic>:flare:<peak BTJD, 2 dp>`.
- `cutouts` are all `null` (no pixel data in this pipeline yet).

## Cache

`~/.cache/planet-hunter/pipeline` (override with `HUNTER_CACHE_DIR`). FITS files are kept for good; the MAST
product list for 6 h; TIC rows for 30 days; catalogue answers for 7 days. `--refresh` re-queries.

## Tests

```bash
uv run pytest                                  # offline, synthetic light curves
uv run pytest --run-network -m network         # real TESS data; writes reports/
```

# vet: skyvet, citable vetting for Planet Finder candidates

`skyvet` takes a Planet Finder (HUNT) candidate and vets it with published, citable tools and catalogues.
It adds a `vetting` block and a verdict. It never changes the candidate's own fields, and it never calls
anything a planet: a `pass` means only that none of these tests found a reason to doubt the candidate.

```bash
cd vet && uv sync
uv run skyvet candidate.json                  # prints the vetting block as JSON
uv run skyvet candidate.json -o vetted.json   # also writes the candidate with its vetting block
uv run skyvet candidate.json --no-triceratops # skip the slow step (reported as not run, so never a pass)
uv run pytest                                 # offline, on recorded real data
```

```python
from skyvet import vet_candidate
vetted = vet_candidate(candidate_json)        # returns a copy with candidate["vetting"]
```

The input needs `tic`, `period_d`, `t0_btjd` (BTJD) and `duration_h`. It should also have `depth_ppm` and
`sectors`, as every HUNT `candidates/<tic>_<n>.json` does.

## The vetting block

```text
leo:          {ran, passed, flags: [...], version, disposition, pixel: {ran, offset_arcsec, ...}, not_evaluated, metrics}
triceratops:  {ran, fpp, nfpp, version, classification, top_scenarios, N, runtime_s}
gaia:         {ruwe, neighbours: [{source_id, sep_arcsec, gmag, required_depth, could_mimic}], binary_hint, nss_orbit}
variability:  {vsx_match, gaia_variable, vsx_ran, gaia_ran}
summary:      {verdict: "pass" | "flag" | "fail", reasons: [...], notes: [...]}
runtime_s:    per step and total
```

A tool that cannot run says `ran: false` with the reason, and that reason becomes a `flag`. Nothing passes
silently. A LEO test whose key metric came out NaN (NaN never trips a threshold) is listed in
`not_evaluated`, and that is a flag too.

## Tools

| Block | Tool / catalogue | What it checks | Cite |
|---|---|---|---|
| `leo` | [LEO-vetter](https://github.com/mkunimoto/LEO-vetter) 1.2.0 | 13 false-alarm and 4 false-positive light-curve tests, with LEO's default thresholds. Plus the pixel-level **off-target** test: a transit difference image from a 21×21 TESScut FFI cutout per sector ([transit-diffImage](https://github.com/stevepur/transit-diffImage), S. Bryson), fitted with the TESS PRF; it fails when the source is > 15″ from the target | Kunimoto et al. 2025 (LEO-vetter); Bryson et al. 2013 (difference imaging) |
| `triceratops` | [TRICERATOPS](https://github.com/stevengiacalone/triceratops) 1.1.0 | Bayesian FPP and NFPP over the target and every TIC star within 10 pixels, with a Gaia DR3 background population | Giacalone & Dressing 2020; Giacalone et al. 2021 |
| `gaia` | Gaia DR3, ESA archive TAP | RUWE, non-single-star solutions and their orbits, and the neighbours within 63″ that could produce the dip | Gaia Collab. 2023; Lindegren et al. 2021 (RUWE); Arenou et al. 2023 (NSS) |
| `variability` | AAVSO VSX (VizieR B/vsx) + Gaia DR3 variability | Known variables within 42″; Gaia classes; Gaia eclipsing binaries within 63″, with a period match | Watson et al. 2006; Eyer et al. 2023; Mowlavi et al. 2023 |

Light curves come from MAST through lightkurve: SPOC 2-min PDCSAP, else TESS-SPOC, else QLP, using the
newest 3 of the candidate's sectors. They are flattened with a Savitzky-Golay filter (window max(0.75 d,
3 × duration), transits masked) for LEO and TRICERATOPS.

### Rules worth knowing

- **Neighbours that could produce the dip.** A neighbour qualifies if eclipsing all of its light would give
  the observed depth: depth × 10^(0.4 ΔG) ≤ 1. The aperture is assumed to hold both stars in full, which is
  the conservative case.
- **Gaia orbits.** For a spectroscopic (SB1) orbit, the mass function gives the companion's minimum mass
  (sin i = 1, host mass from the TIC). At the candidate's period (1 %, ×2 or ×½):
  - ≥ 0.075 M☉ is the dip's stellar eclipsing binary, so the verdict is `fail`.
  - < 13 M_Jup is the transiting planet's own reflex motion. That supports the candidate and is not
    counted as a binary hint.
- **TRICERATOPS** runs in a child process with a wall-clock budget (default 900 s, `--tri-budget`). Past
  the budget it is killed and reported as not run. It uses a fixed seed, so a replay reproduces the numbers.
  N defaults to TRICERATOPS' own 10⁶ (`--tri-n`).
- **TRICERATOPS needs its Gaia background population.** Without it, TRICERATOPS silently drops its
  background scenarios (DTP, DEB, BTP, BEB), so skyvet refuses to record such inputs. astroquery's Gaia
  client needs a CA bundle; on a python.org Python without one, skyvet points `SSL_CERT_FILE` at certifi's
  bundle, and verification stays on.
- **SPOC apertures for TRICERATOPS** are read from the light-curve file's APERTURE extension. TRICERATOPS'
  own lookup scrapes an archive listing that no longer answers. QLP sectors use TRICERATOPS' default
  5×5 box.

## Verdict

| Verdict | When |
|---|---|
| **fail** | any of:<br>• LEO false-positive test (off-target, significant secondary, radius too large, V-shaped, odd-even)<br>• TRICERATOPS NFPP > 0.1 or FPP > 0.5<br>• Gaia orbit at the candidate's period needs a stellar companion<br>• catalogued eclipsing binary at the candidate's period (VSX within 42″, Gaia within 63″) |
| **flag** | any of:<br>• a tool or part did not run, or a LEO test could not be evaluated<br>• LEO false-alarm test. HUNT's own detection cuts already passed, so this calls for a look, not a disposition<br>• TRICERATOPS not validated (FPP ≥ 0.015 or NFPP ≥ 0.001)<br>• Gaia binary hint<br>• known variable at the target that is not the candidate<br>• neighbours bright enough to produce the dip, with neither TRICERATOPS nor the pixel test run to weigh them |
| **pass** | every tool ran and none of the above |

## Cache

Every network call goes through one cache: `~/.cache/planet-hunter/vet`, or `$SKYVET_CACHE_DIR`. It holds
TIC rows, light curves (as arrays), difference images, the interpolated PRF, TRICERATOPS' inputs, the Gaia
field and orbits, and VSX. Entries never expire, since they are all versioned public products. Raw TESScut
cutouts (~100 MB each) are kept in `~/.cache/planet-hunter/vet-work` (`$SKYVET_WORK_DIR`), so each is
downloaded once. `SKYVET_OFFLINE=1` turns any cache miss into an error. Only free public services are used:
MAST, TESScut, ESA Gaia archive, VizieR/CDS and archive.stsci.edu.

## Tests

`uv run pytest` runs offline with `SKYVET_OFFLINE=1` on the real data in `tests/data/cache`, recorded by
`tests/data/record.py`. Every tool re-runs on the recorded inputs and must reproduce
`tests/data/expected.json`. Sockets are blocked during the tests: the only connection allowed (and refused) is
astroquery.gaia's import-time status ping, which carries no data. `SKYVET_TEST_TRICERATOPS=0` skips the slow
TRICERATOPS replay. The recorded cache is 5.4 MB.

## Proof (recorded real data, `tests/data/expected.json`)

| Candidate | Verdict | LEO-vetter | Pixel offset | TRICERATOPS FPP / NFPP | Gaia DR3 | Why |
|---|---|---|---|---|---|---|
| **WASP-18 b** (TOI-185.01, confirmed) | **flag** | FA: sinusoidal variations | 1.0″ | 0 / 0: validated (raw FPP −1.0e-14, rounding) | SB1 orbit at P, ≥ 10.5 M_Jup (planetary); RUWE 0.95 | Every FP test and TRICERATOPS clear it. LEO's SWEET test picks up WASP-18 b's real phase curve (ellipsoidal + beaming from a 10 M_Jup planet on a 0.94 d orbit). |
| **TOI-4257.01** (TFOPWG FP, NEB) | **fail** | FP: off-target | 23.1″ (sectors 89, 63, 62: 24.5″, 23.1″, 27.2″) | 1.0 / 0.329: likely nearby FP | the star at the fitted position is TIC 75208617 = Gaia DR3 5423774792624492928 (G = 14.32), 25.0″ from the target, 2.2″ from the fit | ExoFOP: "offset on TIC 75208617 in SPOC s62; retired as TFOP FP/NEB". The pixel test names that same star. TRICERATOPS spreads NFPP over several neighbours, TIC 75208617 among them (NEBx2P 0.054). |
| **TIC 408512382** (HUNT's EB test star) | **fail** | FP: radius too large, FP: significant secondary | 1.3″ | 1.0 / 0: likely FP | SB1 orbit at P = 4.03187 d needing ≥ 0.467 M☉ | An on-target stellar eclipsing binary, found independently by three tools. |
| WASP-126 b (TOI-114.01, confirmed; extra) | **fail** | FP: odd-even transit differences | 1.2″ | 2.6e-15 / 0: validated | RUWE 0.75 | Odd 5,834 vs even 5,992 ppm: 2.7 % apart at 3.2 σ (box), 3.5 σ (trapezoid), 3.6 σ (transit fit). LEO fails anything over 3 σ, with no fractional floor (HUNT's own check needs > 5 % as well), so at MES 240 a 2.7 % difference trips it. |

**Runtime** per candidate, as `runtime_s`. The machine had a load average of 70–100 on 10 cores for most of
this work (other sessions' sweeps), so these are pessimistic.

- **First run** (network, cold cache): 263–540 s. Most of it is the TESScut FFI cutouts for the pixel test,
  about 100 MB per sector (WASP-18 b LEO took 358 s). TRICERATOPS' own inputs take another 40–730 s.
- **Replay from cache:** 28–145 s, of which TRICERATOPS (N = 10⁵) takes 24–80 s.
- **Offline tests:** the whole suite takes about 4 min.

# forecast/ — `skyforecast`

What will a planet-hunter trap (a sphere on the sky) catch in a time window?

```python
from skyforecast import forecast, Providers, Sphere, Window, chance_of_catch, backtest

f = forecast(Sphere(5.0, 2.2, 0.5), Window(start, end),
             Providers(schedule=..., heatmap=..., exposure=..., skybot=...))
f.to_dict()                          # shared-contract Forecast JSON
chance_of_catch(f, "supernova")      # P(at least one) — use this for "1 in N" in the UI
backtest(past_forecasts, discoveries).summary()
```

Every provider is optional and is defined as a `Protocol` in `skyforecast/providers.py`. This
package never imports `sources/`. The tests and examples run against the deterministic fakes
in `skyforecast/fakes.py`, which produce synthetic data only.

```
uv sync
uv run pytest -q
uv run python examples/worked_examples.py
```

## The model

Units: degrees (ICRS), deg², UTC. A rate means catches per deg² per Rubin visit.

**Camera footprint.** LSSTCam covers 9.6 deg², about 3.5° across (Ivezić et al. 2019,
ApJ 873, 111, §2.2). The model uses a circle of the same area:
r_fov = √(9.6/π) = 1.748°.

**Geometry.**
- Sphere area: A = 2π(1 − cos r), in deg².
- f_i is the fraction of the sphere inside pointing i's footprint, measured with a
  4,000-point equal-area Fibonacci grid over the sphere.
- Whether pointing i overlaps at all is decided exactly: separation < r + r_fov.

**Visits** (from the schedule provider):
- q_i is the pointing's `p_exec`, or 0.8 if the provider doesn't give one.
- `rubin_visit_probability` = 1 − ∏ (1 − q_i), over the overlapping pointings.
- `visits` lists the overlapping pointings as {time, band}.
- The expected number of sphere-equivalent visits is V = Σ q_i f_i.

**Base rates** (`rates.py`, from `heatmap.json` plus exposure):
- Each cell's rate is smoothed with a Gamma–Poisson empirical-Bayes prior:
  λ̂ = (n + β·m) / (E + β), where E = visits × pixel area.
- m and β are fitted separately for each type and each stratum:
  - Solar-system types use ecliptic-latitude bands.
  - Galactic and extragalactic types use galactic-latitude bands (0–10°, 10–30°, 30–90°).
- β is floored at 1 visit-equivalent.
- An empty cell therefore forecasts its stratum's mean, never zero.
- The sphere's rate density ρ_t is the mean of λ̂ over the grid points.

**Expected counts:** μ_t = ρ_t · A · V.

**Known solar-system objects** (SkyBoT):
- SkyBoT is queried at the visit epochs: 10-minute buckets, at most 24 queries.
- Objects inside the sphere are passed through, with SkyBoT's class mapped to a CatchType.
- A visit i covers object j when j is inside that visit's footprint and V_j is no fainter
  than the single-visit depth for the band (u 23.9, g 25.0, r 24.7, i 24.0, z 23.3, y 22.1;
  Ivezić et al. 2019, Table 1).
- Each object's catch probability: P_j = 1 − ∏ (1 − q_i), over the visits that cover it.
- For asteroid, NEO, TNO, comet and interstellar objects:
  μ_t = Σ_j P_j + (1 − κ_t) · μ_t^base.
- κ_t (default 0.5; 0 for interstellar) is the share of historical catches that were objects
  already known. Removing it stops those objects being counted twice.

**P(at least one catch)** (`probability.py`):
- **Exact:** P(n = 0) = ∏ (1 − q_i + q_i · e^(−λ f_i)), with λ = μ/V. This uses the
  per-visit (q_i, f_i) pairs that the in-process `Forecast` carries in `coverage`, a field
  outside the contract that is never serialised.
- **Fallback for forecasts read back from JSON:** a zero-inflated Poisson,
  P_visit · (1 − e^(−μ/P_visit)).

**When inputs are missing** (always written into `inputs_used` as `no:<input> (<why>) - <consequence>`):

| Missing input | Consequence |
|---|---|
| Schedule | V = climatological visits per day from exposure × window length in days, and P_visit = 1 − e^(−V) |
| Schedule and exposure | Counts are per single visit, and P_visit = `null` |
| Exposure only | Heatmap counts are assumed to come from 1 visit per pixel |
| Heatmap | Only known solar-system objects are forecast |
| SkyBoT | Base rates only |

A provider that raises is treated the same as one that is missing.

## Backtest (`backtest.py`)

A discovery counts toward a forecast when `detected_at` is in [start, end) and it lies inside
the sphere. The harness reports:

- **The "1 in 10" check.** Forecasts are binned by P(≥1) and each bin compares the predicted
  probability with the observed frequency, using Wilson intervals. Also reported: the Brier
  score.
- **O/E per type.** Observed ÷ expected counts, with the variance widened for visit
  uncertainty. A type is flagged only if the miss is significant *and* bigger than 10%.
- **Randomized PIT histogram.** A dispersion check whose variance should be about 1/12.
- **Visit-probability calibration** (optional), when actual visits are supplied.

One Bonferroni correction covers every test, so an honest forecaster is flagged about 5% of
the time. `types=` restricts scoring to types whose sources are live.

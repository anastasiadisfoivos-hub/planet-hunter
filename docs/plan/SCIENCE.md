# SCIENCE: the pipeline end to end

data → detrend → search → vet → cross-match → rank → submit

Research date 2026-09-26. Every external claim has a link; **unverified** marks what could not
be confirmed from a fetched source. Counts marked **[ExoFOP 2026-09-26]** are our own counts from
the ExoFOP-TESS CTOI and TOI tables downloaded that day
([CTOI CSV](https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=csv),
[TOI CSV](https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv)), not
published figures.

"Today's code" means `hunt/` on branch `deephunt` plus `pipeline/` (`hunter`) and `pixels/`
(`skypixels`); see `hunt/README.md` there for every threshold.

## 0. Principles

1. **Candidate, never discovery.** A signal is a candidate until others confirm it.
2. **Adopt community tools** for vetting and validation (LEO-vetter, TRICERATOPS, Gaia), so a
   TOI vetter sees numbers they already trust. Keep our own code where it already exists and is
   tested (stitching, the long-period and single/duo search, the pixel check).
3. **Measure before scaling.** Recovery of known planets, injection-recovery and false-alarm rate
   are exit tests ([ROADMAP.md](ROADMAP.md)), not afterthoughts.
4. **Few and solid beats many.** The CTOI promotion rate varies from 0 % to 90 % by uploader
   (§8); a small open project earns trust only with a high rate.

---

## 1. Data

### What we use, and what we don't

| Source | Mags | Cadence | Latency after observation | Access | Licence | Use |
|---|---|---|---|---|---|---|
| **TESS SPOC 2-min / 20-s** light curves + TPFs + DV | ~8,000 targets at 2-min and ~2,000 at 20-s per sector in Cycle 9 ([Cycle 9 call](https://heasarc.gsfc.nasa.gov/docs/tess/docs/TESS_Cycle9_D3CS.pdf)) | 120 s, 20 s | ~4–5 weeks after sector end (S106 ended ~9 Aug 2026; non-FFI ingest started 10 Sep 2026, [MAST holdings](https://outerspace.stsci.edu/spaces/TESS/pages/35094700/TESS+Holdings+Available+by+MAST+Service); inferred from one sector) | astroquery.mast, lightkurve, bulk scripts, `s3://stpubdata/tess` ([AWS registry](https://registry.opendata.aws/mast-tess/)) | public domain, acknowledge ([MAST data use](https://archive.stsci.edu/publishing/data-use)); "no exclusive-use period" ([Cycle 9 call](https://heasarc.gsfc.nasa.gov/docs/tess/docs/TESS_Cycle9_D3CS.pdf)) | **search + vet** (best photometry; TPFs for pixels) |
| **TESS-SPOC FFI** HLSP | T ≤ 13.5 (+ H ≤ 10, d < 100 pc), ≤ ~160k/sector | 1800/600/200 s | lags: MAST page lists S1–85 only (updated 2026-07-23) ([HLSP](https://archive.stsci.edu/hlsp/tess-spoc)) | as above, `s3://stpubdata/mast/hlsp/tess-spoc` (search summary, unverified) | CC BY 4.0 | **search** (archival sectors) + DV reports |
| **QLP** HLSP | T < 13.5 (+ select fainter M dwarfs from S41) | 1800/600/200 s | "a few weeks" after sector end ([QLP](https://tess.mit.edu/qlp/)); S1–104 online ([HLSP](https://archive.stsci.edu/hlsp/qlp)) | as above | CC BY 4.0 | **search** (most complete, most timely FFI set); TGLC photometry since S94 ([DRN 004](https://arxiv.org/abs/2603.22236)) |
| **TGLC** | all Gaia DR3 stars to **T = 16** | FFI cadence | MAST HLSP S1–55 only; newer sectors via `pip install tglc` ([HLSP](https://archive.stsci.edu/hlsp/tglc), [GitHub](https://github.com/TeHanHunter/TESS_Gaia_Light_Curve); [Han & Brandt 2023](https://arxiv.org/pdf/2301.03704)) | bulk scripts / DIY from FFIs | CC BY 4.0 | **search** faint M dwarfs (Phase 7) |
| TICA quick-look FFIs | all | 200 s | ~1 day after each orbit ([TICA](https://archive.stsci.edu/hlsp/tica)) | bulk, TESSCut | not stated | only if we run our own photometry |
| GSFC-ELEANOR-LITE, T16 | T < 16 | FFI | S1–26 only / Cycle 1 only ([ELEANOR-LITE](https://archive.stsci.edu/hlsp/gsfc-eleanor-lite), [T16](https://arxiv.org/abs/2502.13792)) | HLSP | CC BY 4.0 | not now (already searched by their teams) |
| Kepler / K2 | Kp ~9–16 | 29.4 min / 1 min | complete ([MAST Kepler](https://archive.stsci.edu/missions-and-data/kepler), [K2](https://archive.stsci.edu/missions-and-data/k2)) | astroquery, lightkurve, S3 | public domain | not in the nightly loop; K2 re-search still yields candidates ([Kruse 2019](https://arxiv.org/abs/1907.10806): 374 new; [Zink 2021](https://arxiv.org/abs/2109.02675): 366 new) but CTOIs are for TESS |
| **Gaia DR3** | G ~3–21 | catalogue | released 2022; **DR4 on 2 Dec 2026** ([DR4](https://www.cosmos.esa.int/web/gaia/data-release-4)) | TAP `https://gea.esac.esa.int/tap-server/tap`, astroquery.gaia | **CC BY-NC 3.0 IGO** ([licence](https://www.cosmos.esa.int/web/gaia-users/license)) — non-commercial | **vet**: R★/Teff, RUWE, neighbours, EB table (2.18 M), NSS (~813 k) ([DR3](https://www.cosmos.esa.int/web/gaia/dr3)) |
| **ESO archive HARPS / ESPRESSO** | bright stars | irregular | ~1-yr proprietary; NIRPS-GTO HARPS precise RVs 2 yr ([policy](https://archive.eso.org/cms/eso-data-access-policy.html), [HARPS release](https://www.eso.org/rm/api/v1/public/releaseDescriptions/72)) | TAP `archive.eso.org/tap_obs`, pyvo, astroquery.eso; RV in `QC CCF RV` header | CC BY 4.0 | **vet only**, when archival RVs exist; ready catalogues: [Barbieri 2023](https://arxiv.org/abs/2312.06586) (289,843 obs, 6,488 objects), [HARPS-RVBank](https://github.com/3fon3fonov/HARPS_RVBank) (CC0; counts unverified) |
| NGTS DR1/DR2 | ≤ 16 | 12–13 s | DR2 (2020) covers 2015–2018; nothing newer found ([ESO news](https://archive.eso.org/cms/eso-archive-news/second-data-release-of-the-next-generation-transit-survey.html)) | ESO portal / TAP | CC BY 4.0 | vet / ephemeris where fields overlap; already citizen-searched ([PH NGTS](https://arxiv.org/abs/2404.15395)) |
| HATSouth | – | – | only confirmed-planet and K2-C7 light curves public ([hatsurveys](https://hatsurveys.org/data.html)); **no survey DR1 confirmed** | – | not stated | not useful except known planets |
| WASP-South / SuperWASP DR1 | V ≲ 15 | minutes (unverified) | DR1 = 2004–2008, ~18 M LCs ([NEA](https://exoplanetarchive.ipac.caltech.edu/docs/SuperWASPMission.html), [CERIT](https://wasp.cerit-sc.cz/)) | NASA Exoplanet Archive TAP | acknowledge | vet: EB check / ephemeris for bright candidates |
| KELT (incl. South) | bright | 20–30 min | 28 fields, 2006–2018 ([NEA](https://exoplanetarchive.ipac.caltech.edu/docs/KELT.html)) | NEA TAP | acknowledge | vet |
| MEarth-South | nearby M dwarfs | – | DR11 (2014–2022) ([DR11](https://lweb.cfa.harvard.edu/MEarth/DataDR11.html)) | tar | cite | vet for M-dwarf hosts |
| SPECULOOS | ultracool dwarfs | – | **no public light-curve release confirmed** | – | – | not useful |
| Rubin / LSST | r ≳ 16 | sparse (days) | alerts public since Feb 2026 via brokers ([Rubin](https://rubinobservatory.org/news/first-alerts)); DP2 data-rights only; DR1 ~June 2028 | brokers | alerts public | **not useful** for TESS-depth transits |

### Choice per star and sector (today's code, kept)

Per sector, the best available product: SPOC 2-min → TESS-SPOC FFI → QLP
(`hunter.choose_products`), each normalised by its own median, default quality mask, momentum
dumps and background kept for vetting. **Change:** read FITS from `s3://stpubdata/tess` (anonymous,
monthly updates, SNS topic for new data; [registry](https://registry.opendata.aws/mast-tess/))
rather than MAST HTTP where the file is there, to cut fetch time and MAST load.

### Failure modes
- **Latency.** Newest sectors are 4–5 weeks old at best for SPOC; TESS-SPOC FFI HLSP is 20+
  sectors behind; TGLC HLSP stops at S55. The search always works on old data; the monitor says so.
- **Product mixing.** Different products and apertures give different depths per sector
  (dilution corrections differ); the `sector_depth` check can fire on real planets (seen on
  TOI-2180 b). Keep the per-dip depth method from DEEPHUNT.
- **MAST stalls.** A star is killed after 15 min (today's code); S3 reads reduce this.
- **Licences.** Gaia is CC BY-NC: the repository and site must say so and stay non-commercial.

---

## 2. Where an independent pipeline can add something

Evidence from published searches and the ExoFOP tables:

| Search | Data / regime | Candidates | CTOIs → promoted to TOI [ExoFOP 2026-09-26] |
|---|---|---|---|
| RAMjET CNN, [Olmschenk 2021](https://arxiv.org/abs/2101.10919) | eleanor FFI, T ~12.5, short P | 181 new | 184 → 165 (**90 %**) |
| Planet Hunters TESS, [Eisner 2021](https://arxiv.org/abs/2011.13944) | SPOC 2-min, citizen inspection | 90 new (73 single transits) | 182 → 118 (65 %) |
| Kruse (CVZ Cycle 2) | – | – | 84 → 31 (37 %) |
| CDIPS, [Bouma](https://arxiv.org/abs/1910.01133) | young cluster stars, T ~13.3 | – | 87 → 19 (22 %) |
| DIAmante, [Montalto 2020](https://doi.org/10.1093/mnras/staa2438), [2022](https://arxiv.org/abs/2210.14559) | FFI, FGKM | 396 (252 new); 1,160 (842 new) | 1,076 → 155 (14 %) |
| Transformer, [Salinas 2025](https://arxiv.org/abs/2502.07542) | FFI, giants only | 214 new | 207 → 28 (14 %) |
| Single-transit finders (steuer, essack) | singles | – | 179 → 14 (8 %); 146 → 5 (3 %) |
| Duotransits, [Hawthorn 2024](https://arxiv.org/abs/2310.17268) | Y1+Y3, P ≳ 20 d | 85 (60 new) | 58 → 3 (5 %) |
| DTARPS, [Melton 2023](https://arxiv.org/abs/2302.06724) | DIAmante LCs | 462 | 208 → 10 (5 %) |
| PATHOS (Nardiello) | cluster stars | – | 72 → 3 (4 %) |
| NEMESIS, [Feliz 2021](https://arxiv.org/abs/2103.05647) | M dwarfs < 100 pc | 29 (24 new) | 24 → 1 |
| LEO-vetter M-dwarf search, [Kunimoto 2025](https://arxiv.org/html/2509.10619v1) | M dwarfs T < 14, QLP S1–70 | 172 PCs (45 new) | 12 → 0 (yet) |
| RAVEN, [Lafarga 2026](https://arxiv.org/abs/2603.22597) | TESS-SPOC FFI S1–55, 2.2 M stars | >2,000 (~1,000 new); 118 validated | 1,173 → 0 (yet; uploaded 2026-08-27) |
| T16, [Roth 2026](https://arxiv.org/abs/2604.18579) | Cycle 1 FFI to T = 16 | 11,554 (10,091 new) | 19 → 0 (yet) |
| QLP Faint-Star, [Kunimoto 2022](https://arxiv.org/abs/2112.02176) | QLP, T 10.5–13.5 | – | official: 3,928 "FAINT" TOIs today |
| SHERLOCK "Hidden Gems", [2026](https://arxiv.org/abs/2601.21774) | extra planets in known M-dwarf systems | TOI-237 c, TOI-4336 A c confirmed | – |
| [Tschudi 2026](https://arxiv.org/abs/2603.10247) | single-author TLS + TRICERATOPS, M3–M6 | 20 signals / 16 systems | reported **17.4 % false-alarm rate** |

Totals: 5,137 CTOIs, **813 promoted (15.8 %)**; ~50 promotions a year recently (2024: 55,
2025: 42, 2026 to Sept: 50) [ExoFOP 2026-09-26]. In the Prime Mission, "All CTOIs which have been
promoted to TOIs were also TCEs in the SPOC pipeline or the QLP" ([Guerrero et al. 2021 §8.4](https://arxiv.org/abs/2103.12538)).

TOI catalogue gaps [ExoFOP 2026-09-26]: 8,148 TOIs; only **457 with Tmag ≥ 13.5**; only **220 with
P = 30–100 d and 132 with P > 100 d**; 112 with no period.

**Conclusions for us**
- **Saturated:** P < ~16 d around FGK stars at T < 13.5 (SPOC, QLP multi-sector + faint-star,
  RAVEN, DIAmante, ExoMiner++). Independent CTOIs there promote at 5–14 %.
- **Realistic niches**, in order of fit with today's code:
  1. **Long periods (P ≈ 20–200 d) with ≥ 3 transits from multi-year stitching** — today's
     `bls_long` + TLS on all sectors is built for this; the catalogue is thin there.
  2. **Duotransits** across the year gaps (already coded, `singles.py`); TIaRA predicts 113
     biennial duotransits from Y1+Y3 alone ([Rodel 2024](https://arxiv.org/abs/2402.07800));
     plain singles promote poorly (3–8 %), so singles are shown but not submitted without a
     period constraint.
  3. **Extra small planets in known systems** (sibling search, list B, already coded), as in
     SHERLOCK Hidden Gems.
  4. **Faint M dwarfs, T 13.5–16**, via TGLC (Phase 7): QLP still stops at T = 13.5; competition
     is T16 (Cycle 1 only) and LEO (T < 14). Follow-up is harder.
- The 90 % case (RAMjET) was short-period and probably overlapped QLP TCEs; the TOI team
  promotes what its own vetting can reproduce. So every CTOI must come with a reproducible
  vetting report on public light curves.

---

## 3. Detrend

**Tool:** wotan time-windowed biweight ([wotan](https://github.com/hippke/wotan), MIT; no
release since 2021), today's code. Split at gaps > 0.5 d; known and found transits masked out of
the trend; window = 3 × the longest duration searched (0.9 d short search; ≥ 3 d long search;
0.5/1.5/3 d for the dip tiers).

**Why:** robust to transits, standard in TESS searches, cheap. A Sept 2026 PLATO benchmark found
a Huber-spline over several window sizes plus CETRA matched the best (GP-based) method
(61.3 % vs 61.2 % recovery) ([arXiv:2609.15493](https://arxiv.org/abs/2609.15493)); evaluate a
multi-window Huber spline in Phase 1 if long-duration transits are being eaten.

**Failure modes**
- Window too short for long-duration transits (long periods around large stars) → depth
  suppressed; mitigated by the 3× rule, measured by injection.
- Fast rotators / flares (active M dwarfs) leave residuals → false dips; `nuance`
  ([arXiv:2402.06835](https://arxiv.org/abs/2402.06835)) is the fallback for those stars only
  (expensive, GPU).
- Sector-edge ramps and scattered light → dips at edges; handled by the `edge`, `background` and
  `shape` checks.

## 4. Search

**Tools (today's code):**
- `bls_short`: astropy BLS two-pass, 0.5–15 d.
- `bls_long`: BLS on an Ofir-2014-spaced frequency grid, 15 d – half the baseline, 180 s budget.
- `tls`: Transit Least Squares ([Hippke & Heller 2019](https://github.com/hippke/tls), MIT),
  0.5 d – half baseline, limb-darkened template; capped at 60 s predicted cost (runs on the newest
  sectors that fit).
- up to 3 signals per star, iterative masking; re-measured on native cadence.
- Single/duo dip search: box matched filter, 1–24 h, SES ≥ 7; trapezoid refit; period from
  duration + stellar density (Monte Carlo with Kipping 2013 eccentricity prior).
- Known planets on the star are masked (fixed ephemeris + located transits + leak check) so the
  search looks for *additional* planets.

**Why:** BLS is fast and standard; TLS is more sensitive to small planets; long-period grid and
dip search target the niches of §2.

**Options to evaluate (Phase 1–2), not adopt blindly:** CETRA (GPU; ≥ 20 % more low-SNR
transits than TLS, far faster; [arXiv:2503.20875](https://arxiv.org/abs/2503.20875)) and GPU BLS
(`cuvarbase`, used by the LEO M-dwarf search). Free runners have no GPU; Kaggle does (30 h/week).

**Failure modes**
- **TLS truncation.** On many-sector stars TLS runs only on the newest sectors that fit 60 s;
  small long-period planets rely on BLS. The benchmark shows TLS is the largest single cost
  (§9).
- **Long-period recovery collapse.** In the committed sensitivity run (`hunt/results/
  sensitivity.json`, 200 stars, 2,000 injections, earlier 3-sector search), 10–15 d injections
  were detected 77 % of the time but passed every cut only 6.6 %; 7–10 d: 84 % vs 45 %. Must be
  diagnosed (ROADMAP Phase 1c).
- **Aliases** (P/2, 2P, 3P) and period errors over multi-year baselines → wrong ephemeris
  submitted; `period_alias` check and fine re-fit over ± one duration of drift exist.
- **Systematics at 13.7 d and its harmonics** (orbital period of TESS) and momentum dumps.
- **Look-elsewhere:** thousands of periods × durations × stars → false alarms; thresholds must be
  set from inverted/scrambled light curves (Phase 1 exit test), not by eye.

## 5. Vet

Order: cheap flux-level tests on every signal → pixel tests on survivors → statistical
validation on candidates → archival and human review.

| Stage | Tool | Inputs | Cost | Why |
|---|---|---|---|---|
| Flux-level (ours) | `hunt` checks: snr, odd_even (per-dip), secondary_eclipse, size, period_alias, momentum_dump, sector_depth, duration (vs ρ★), three_dips, per-dip edge/shape/background, neighbour_dips | light curve, ephemeris, TIC ρ★/R★ | seconds (vetting is 0.1–0.2 s per star in our runs) | already built and tested on real false alarms |
| Flux-level (adopt) | **LEO-vetter** ([Kunimoto 2025](https://arxiv.org/html/2509.10619v1), [GitHub](https://github.com/mkunimoto/LEO-vetter), GPL-3.0, v1.2.0 2026-07): 13 tests incl. SWEET, model-fit AIC, asymmetry, single-event domination, V-shape, secondary, odd-even, Rp < 22 R⊕ | time, flux, err; P, T0, duration; M★, R★ | not stated (**unverified**); built for ~20k TCEs | Robovetter-style tests the TOI team knows; reported 91 % completeness, 97 % reliability vs false alarms; passed 125/135 known PC/CP TOIs |
| Pixel-level | **`skypixels`** (ours): difference image per sector, PSF-fitted centroid vs target and every Gaia neighbour, "depth needed" per neighbour, verdict | SPOC TPF or TESScut, ephemeris, Gaia DR3 | ~1 min cold, ~1 s warm per candidate (`pixels/reports/runtime.json`) | #1 false-positive source is a nearby EB |
| Pixel-level (adopt) | LEO-vetter centroid test (offset < 15″) via `transit-diffImage` | TPF, sector | – | cross-check with ours; disagreements go to human review |
| Contamination | **TESS-cont** ([Castro-González 2024](https://arxiv.org/abs/2409.18129); licence to check) or `tpfplotter` ([GitHub](https://github.com/jlillo/tpfplotter), MIT) | TIC, sector | light | the standard TFOP figure; which neighbour could host the dip |
| Statistical | **TRICERATOPS** ([Giacalone 2020](https://arxiv.org/abs/2002.00691), [docs](https://triceratops.readthedocs.io/en/latest/tutorials/example.html), MIT, v1.1.0 2026-09) | TIC, sectors, aperture, folded LC (~100 pts), P, depth; optional contrast curve | ~1–5.5 min per run; the docs' 20 runs take ~20 min | FPP/NFPP the community uses; validation needs FPP < 0.015 and NFPP < 10⁻³, which we will **not** claim without high-res imaging; we report the numbers |
| Stellar / binarity | **Gaia DR3**: R★, Teff, RUWE, NSS, `vari_eclipsing_binary`, neighbours | TAP | light | radius sanity, unresolved binaries (RUWE threshold 1.4 is common but **unverified** here), known EBs |
| Archival RV | ESO archive (ObsCore cone search + Barbieri 2023 catalogue) | coordinates | light | rules out stellar/brown-dwarf companions when spectra exist |
| Archival photometry | SuperWASP DR1, KELT, NGTS DR2, MEarth (where overlapping) | coordinates | light | EB depth/secondary on longer baselines |
| ML cross-check | ExoMiner++ / 2.0 ([2502.09790](https://arxiv.org/abs/2502.09790), [2601.14877](https://arxiv.org/abs/2601.14877); FFI ROC AUC 0.995) | SPOC DV-like products | GPU | a second opinion; never a gate |
| Human | two reviewers, written checklist (dossier order, PRODUCT.md §3); optional LATTE plots ([GitHub](https://github.com/noraeisner/LATTE)) | dossier | ~15 min/candidate | what made Planet Hunters' CTOIs promote at 65 % |

**Do not adopt:** VESPA (unmaintained since 2019), original Astronet repos (2019).

**Failure modes**
- **Could-not-run treated as pass.** Today's code already reports `null` and requires must-run
  checks; keep that for every new tool.
- **Crowded fields** (faint stars, Galactic plane): pixel centroids inconclusive; TRICERATOPS NFPP
  high. Such candidates are labelled and not submitted without extra evidence.
- **Thresholds tuned for FGKM dwarfs** (LEO) mis-vet giants and subgiants; we exclude giants
  from submission.
- **Over-vetting** kills real planets (e.g. `sector_depth` on TOI-2180 b before DEEPHUNT's fix).
  Phase 3 exit test measures planet retention on CP/KP TOIs.

## 6. Cross-match

**Tools:** today's `hunter.known` + `hunt` catalogue snapshot: confirmed planets (NASA
Exoplanet Archive), TOIs and CTOIs (ExoFOP), TESS EB catalogue; matched by period (1 % or
×2, ×3, ½, ⅓) on the star and on any listed star within 2.5′; lists downloaded daily and
snapshotted per run. **Add:** Gaia DR3 `vari_eclipsing_binary` and NSS orbits; SPOC and QLP
TCE lists / DV reports on the star (exo.MAST), so we know whether the TESS pipelines saw it
(the TOI team promotes what they can reproduce, §2).

**Failure modes**
- Lists lag: a TOI released after our snapshot → we "find" a known object. Re-check at ingest
  (exists in `finder_ingest`) and again before submission.
- Ephemeris drift / TTVs hide a match (TOI-1130, TOI-181 cases in today's tests).
- A neighbour's EB at a different TIC but the same period: the 2.5′ neighbour match catches
  listed ones; pixels catch unlisted ones.

## 7. Rank

**Today's score** (0–1): `K_kind × (0.40·S_snr + 0.20·S_orbit + 0.25·S_checks +
0.15·S_brightness) × 0.8 if single-sector`; singles ≤ 0.24, duos ≤ 0.5.

**Change:** rank for *likelihood of becoming a TOI and being followed up*, not only SNR:
- gates first (all vetting passed, pixel verdict `on target`, TRICERATOPS NFPP < 10⁻³ reported),
- then a score adding: TRICERATOPS FPP (lower better), niche value (P > 20 d, small star, small
  planet), follow-up feasibility (Tmag, depth vs ground-photometry precision, predicted
  transits in the next 6 months), and whether a SPOC/QLP TCE exists.
Weights are set by testing on known TOIs (CP/KP vs FP) in Phase 3, not by hand.

**Failure mode:** a hand-tuned score looks precise and isn't; publish the weights, the
calibration test, and show score parts in the dossier (already done for today's score).

## 8. Submit (ExoFOP CTOI)

### The answer: is a refereed paper required? **Yes, since 19 August 2026.**

ExoFOP news ([news.php](https://exofop.ipac.caltech.edu/tess/news.php), fetched 2026-09-26):

> March 31, 2026 — "ExoFOP has temporarily paused the functionality for users to upload new
> planet candidates (CTOIs and other projects)."

> August 19, 2026 — "ExoFOP has reopened support for community planet candidates from TESS,
> Kepler, K2, and beyond. To ensure the quality and utility of candidates uploaded to ExoFOP for
> the community, going forward candidates must first be published in a peer-reviewed journal
> with online access before being uploaded to ExoFOP, and approval to upload candidates is
> required."

Candidate guidelines ([candidate_help.php](https://exofop.ipac.caltech.edu/tess/candidate_help.php)):

> "ExoFOP will only allow upload of Community Candidates accepted and published in the refereed
> literature. The URL link to the paper must be provided."

> "Paper URL (required): Enter the URL link to the published paper with your candidate."

> "For cTOI (TESS data source) consideration by the TESS Object of Interest working group, all
> four of orbital period, transit epoch, transit depth, and transit duration must be included
> and greater than zero (0)."

Bulk upload template ([params_planet_YYYYMMDD_001.txt](https://exofop.ipac.caltech.edu/tess/templates/params_planet_YYYYMMDD_001.txt)):
"paper = url of published paper for candidates - required for flag = newctoi"; "prop_period …
Must be 0 for new CTOIs"; "notes … maximum 120 characters (required if new CTOI…)".

Before the change the paper was only recommended (Wayback copy of help.php, 2025-04-04): "The best
CTOIs are ones that are published in the astrophysics refereed literature… If the CTOIs are based
upon a refereed paper, include an html link to the paper in the Notes." (via the research agent;
the archived page itself was not re-checked here).

The MIT TOI FAQ still says "If you find a planet candidate submit it to ExoFOP-TESS. Your
candidate will become a community TOI (cTOI). The candidate will be reviewed by the TESS TOI Team
where if it meets the team standard it will be assigned TOI number"
([TOI release FAQ](https://tess.mit.edu/toi-releases/toi-release-faqs/)). That describes review,
not upload rights; ExoFOP controls uploads, so **the FAQ is out of date on this point**, and
FINDER-API's claim was right.

Accounts ([account.php](https://exofop.ipac.caltech.edu/account.php)): for people "conducting
astronomical observational, modelling, or theoretical work at a level consistent with publication
in a professional journal"; approval is manual; "Citizen Scientist" is a listed position.
Upload rights need a second approval via
[pub_candidate_upload_request.php](https://exofop.ipac.caltech.edu/tess/pub_candidate_upload_request.php)
(login required; its fields are **unverified**).

### What makes a CTOI get promoted to a TOI
- "The vetting team may promote a CTOI to a TOI if the CTOI identifies a quality planet candidate
  from the SPOC or QLP pipeline mistakenly ruled out in the triage or vetting process"; 169 Prime
  Mission CTOIs were promoted, 106 of them TCEs wrongly dropped in triage, and all promoted CTOIs
  were also SPOC or QLP TCEs ([Guerrero et al. 2021, §8.4](https://arxiv.org/abs/2103.12538)).
- The written criteria are not public beyond "if it meets the team standard" (FAQ above). No
  published timeline; the CTOI table has no creation date, so lag cannot be measured
  [ExoFOP 2026-09-26].
- Empirically: promotion rate by uploader ranges from 0 % to 90 % (§2); ~50 promotions a year.

### Our submission path (see ROADMAP Phases 5–6)
1. Candidates pass §5 vetting and two human reviewers.
2. A refereed catalogue paper (with a professional co-author, ideally a TFOP member) is accepted.
3. ExoFOP account + upload approval.
4. Upload with the existing exporter (`POST /finder/export/ctoi`: pipe-delimited bulk file,
   `flag=newctoi`, `disp=PC`, `prop_period=0`, period/epoch/depth/duration all > 0, paper URL,
   notes ≤ 120 chars stating the pixel verdict, next free `.nn` per TIC).
5. Track outcomes daily from the CTOI/TOI tables.

**Failure modes:** uploading before a paper (not possible now); weak candidates damaging the
uploader's track record; ephemerides that expire (propagate the epoch uncertainty and give
predicted times); duplicate submissions of objects that became TOIs meanwhile (re-check lists
the same day).

## 9. Compute budget

### Measured (2026-09-26)

Code: `origin/deephunt` `30bbe36`, `hunt run --workers 1`, cold caches, known-list snapshot
passed in. Sample: 12 stars at evenly spaced ranks 500 … 46,150 of the ranked target list
(730,799 stars), i.e. inside the "best 50,000"; **8 finished** before the run was stopped (the
machine was shared with other jobs at load average 35–85, so wall times are inflated and CPU time
per star was sampled instead). Raw numbers: [evidence/bench_2026-09-26.json](evidence/bench_2026-09-26.json).

| | value |
|---|---|
| CPU time per star (whole search: stitch, 3 periodic searches, measure, checks, dip search) | mean **109 s**, median 107 s, range 48–180 s (n = 8, Apple Silicon core) |
| Download (cold) per star | 12–26 s (4–7 sectors) |
| Largest single cost | TLS (12–233 s wall), then `bls_long`, then re-measuring on native cadence |
| Sectors per star in the sample | 4–7 (median of the top 50k: 7) |
| Cross-check | the owner's own 247-star calibration run (same code, 8 workers on the same machine) averaged 191 s wall per star, 16 s fetch |

### Extrapolation to 20 free GitHub-hosted runners

Assumptions (each is a guess until Phase 2's exit test replaces it with a real Actions run):
- a public-repo `ubuntu-latest` runner has **4 vCPU, 16 GB** ([GitHub docs](https://docs.github.com/en/actions/reference/runners/github-hosted-runners));
  `hunt run` defaults to one worker per CPU, and at ~1–2 GB per star, 4 workers fit;
- a runner vCPU is **1.5–2.5× slower** than an Apple Silicon core for this numpy/astropy work
  (**unverified** assumption);
- downloads overlap with other workers' CPU; each job has a 6 h cap, so the existing 350-min
  budget is kept.

Per runner: 4 workers × 3,600 s ÷ (109 s × 1.5–2.5 + ~15 s I/O) ≈ **50–80 stars/hour**.
**20 runners × 5.8 h ≈ 5,800–9,300 stars per night; planning figure 5,000**, allowing for
many-sector stars (the calibration run shows 10–14-sector stars cost ~30 % more than 5–9) and
MAST stalls.

**Best 50,000 targets: ~10 nights at 5,000/night** (range 6–13), then only stars with new sectors
(a few thousand per sector) need re-searching.

### Can we use hosted runners for this? Policy risk

- Free: "Use of the standard GitHub-hosted runners is free and unlimited on public repositories";
  jobs are capped at 6 h, workflow runs at 35 days, a matrix at 256 jobs and the Free plan at
  **20 concurrent jobs**; scheduled runs "can be delayed", and in public repos are "automatically
  disabled when no repository activity has occurred in 60 days"
  ([billing](https://docs.github.com/en/billing/concepts/product-billing/github-actions),
  [limits](https://docs.github.com/en/actions/reference/limits),
  [events](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)).
- But GitHub's terms say: "Actions should not be used for: … Any activity that places a burden
  on our servers, where that burden is disproportionate to the benefits provided to users …; or
  If using GitHub-hosted runners, any other activity unrelated to the production, testing,
  deployment, or publication of the software project associated with the repository where GitHub
  Actions are used." Misuse "may result in termination of jobs, restrictions…, disabling of
  repositories…, or in some cases, suspension or termination of your GitHub account"
  ([terms, Actions](https://docs.github.com/en/site-policy/github-terms/github-terms-for-additional-products-and-features#actions)).
  A ~7,000 runner-minute nightly science sweep using all 20 concurrent slots is arguably
  "unrelated activity"; no exception for scientific batch compute was found.
- Also: 20 concurrent jobs is the whole Free-plan cap, so CI would queue behind the sweep.

### Free compute options, and the recommendation

| Option | Capacity (docs) | Stars/day (from 109 CPU-s/star × slowdown) | Notes |
|---|---|---|---|
| 20 GitHub-hosted runners, 6 h/night | 80 vCPU | ~5,000 | ToS risk above; recommended only for CI and a small nightly delta |
| **Self-hosted runner** on a machine the owner controls (e.g. this 10-core Mac, idle hours) | 10 cores | ~5,000–8,000 per 24 h (1× slowdown) | Actions still schedules it; the hosted-runner clause does not apply; costs electricity |
| MAST **TIKE** | "TIKE is free to use!", "Four cores" ([TIKE](https://timeseries.science.stsci.edu)); RAM/disk limits **unverified** | ~1,500–2,500 per 24 h if sessions allow long runs (**unverified**) | data is next to the archive; interactive JupyterHub, not a scheduler |
| **Kaggle** notebooks | 12 h sessions, 4 CPU, 30 GB RAM; GPU 30 h/week; scheduled runs allowed ([Kaggle docs](https://www.kaggle.com/docs/notebooks)) | ~1,000–1,500 per 12 h session | GPU could run CETRA/cuvarbase; concurrency limits **unverified** |
| Google Colab free | "not guaranteed and not unlimited", ≤ 12 h; forbids "running distributed computing workers" ([Colab FAQ](https://research.google.com/colaboratory/faq.html)) | – | not suitable for unattended batch |
| Storage: Zenodo (50 GB/record), Cloudflare R2 (10 GB free, no egress fees), GitHub Pages (1 GB) | – | – | release data on Zenodo; frames/results on R2 |
| Data: `s3://stpubdata/tess` | anonymous read, us-east-1 ([registry](https://registry.opendata.aws/mast-tess/)) | – | reduces MAST HTTP load |

**Recommendation:** run the bulk search (the 50,000) on a self-hosted runner and/or Kaggle
scheduled sessions; keep GitHub-hosted runners for CI, for the per-night "new sector" delta
(≤ ~500 stars, ≤ 2 runners), and for the merge/ingest jobs. Ask GitHub Support in writing
before using hosted runners at the 20-job scale.

**Cost levers (Phase 2):** TLS dominates on many-sector stars; run TLS only on signals BLS
already found (period-restricted) or replace it with CETRA on a GPU (Kaggle). Reading FITS from
S3 cuts the fetch share.

## 10. Summary of risks

| Risk | Where | Mitigation |
|---|---|---|
| CTOI needs a refereed paper | §8 | plan Phase 5 as a paper with a professional co-author |
| Hosted GitHub runners' terms | §9 | self-hosted runner / TIKE / Kaggle for the bulk; hosted runners for CI and small deltas |
| Long-period candidates lost to cuts | §4 | Phase 1c |
| False alarms from look-elsewhere | §4 | thresholds from inverted/scrambled runs |
| Gaia licence non-commercial | §1 | state it; stay non-commercial |
| Data latency misread as "live sky" | §1, PRODUCT.md | two clocks on every page |

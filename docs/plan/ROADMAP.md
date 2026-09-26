# ROADMAP: build order for the planet finder

Each phase has a measurable **exit test**. A phase is done when its test passes on real data and
the numbers are committed (JSON under `hunt/results/` or `docs/plan/evidence/`), not when the code
exists. Phases are in build order; later phases assume earlier exit tests hold.

Science background for every stage is in [SCIENCE.md](SCIENCE.md); pages in [PRODUCT.md](PRODUCT.md);
cleanup in [REMOVE.md](REMOVE.md).

## Two facts that shape this roadmap

1. **ExoFOP now requires a refereed paper before a CTOI can be uploaded** (news item of
   2026-08-19; details and quotes in [SCIENCE.md §8](SCIENCE.md#8-submit-exofop-ctoi)). The
   route to a TOI therefore goes through a published, peer-reviewed candidate paper and an
   approved ExoFOP upload account. That makes Phases 5–6 a publication project, not a button.
2. **Uploader track record matters.** Of 5,137 CTOIs on ExoFOP (downloaded 2026-09-26), 813
   (15.8 %) were promoted to TOIs, but the rate by uploader ranges from 0 % to 90 %
   ([SCIENCE.md §8](SCIENCE.md#8-submit-exofop-ctoi)). Few, well-vetted candidates beat many
   weak ones. The roadmap therefore spends its effort on validation (Phases 1 and 3) before
   volume.

---

## Phase 0: One product on `main`

Assemble `main` from the KEEP list in REMOVE.md: `hunt/` (from `deephunt`), `pipeline/`,
`pixels/`, trimmed `api/` (from `finderapi`), trimmed `web/` (from `polish`), `deploy/`,
`.github/workflows/{ci,sweep,finder-ingest,image}.yml`. Keep the (correct) ExoFOP
"refereed paper required" wording in `finder_export.py` / `api/README.md` and add the source date.

**Exit test**
- `ci.yml` green on `api pipeline hunt pixels web` from a clean clone.
- `grep -rE "events|/sky|/lab|skyevents|skypictures|skysources|skyforecast"` over `api/ web/ .github/`
  returns only intentional hits (changelog, redirects).
- Honesty test extended to the new routes passes (`discovered`, `new planet` banned).
- One manual `sweep` run on 20 stars completes and `finder-ingest` stores its output.

## Phase 1: Prove the search finds what it should (science validation I)

The search code exists (`hunt/`, DEEPHUNT branch). Before scaling, measure it.

1a. **Blind known-planet recovery.** Turn the known-list masking and the `known` filter off and
run on stars that host TOIs with TFOPWG disposition PC/CP/KP.
1b. **Injection-recovery with the deep search**, all sectors (the committed
`sensitivity.json` is from the earlier 3-sector search).
1c. **Fix the long-period recovery collapse.** In the committed sensitivity run, injections at
10–15 d were *detected* 77 % of the time but *recovered* (passed every cut) only 6.6 %; at 7–10 d,
84 % vs 45 %. Find which stage kills them (likely `≥ 3 transits` on ≤ 3 sectors, `sde`, or
`duration`) and fix or justify it.

**Exit tests**
- Recovers **≥ 90 %** of known TOIs (PC/CP/KP) with SPOC SNR ≥ 10 and P < 15 d at **Tmag < 12**,
  in a fixed sample of ≥ 300 TOI hosts from sectors 1–106 (sample committed), at the TOI's period
  (within 1 %, or a ×2/×½ alias, reported separately).
- Recovers **≥ 70 %** of known TOIs with 15 d < P < 100 d on stars with ≥ 5 sectors.
- Injection-recovery on ≥ 200 quiet dwarfs, all sectors: **recovered/detected ≥ 0.8 in every
  period bin up to 15 d**, and overall recovery for 2–4 R⊕ at P < 10 d on M dwarfs ≥ 70 %.
- False-alarm budget measured: on 1,000 stars with no known signal, **candidates per 1,000 stars**
  at the current thresholds is reported, and scrambled-time (inverted-flux) runs give
  **≤ 1 false candidate per 10,000 stars**.

## Phase 2: Scale the search to the priority list (compute)

Throughput measured on this code ([SCIENCE.md §9](SCIENCE.md#9-compute-budget)): ~109 CPU-s
per all-sector star (n = 8), which extrapolates to ~5,000 stars per night on 20 free hosted
runners × 6 h, so the best 50,000 take ~10 nights (range 6–13). Hosted runners at that scale
carry a GitHub Terms risk, so the bulk should run on a self-hosted runner or Kaggle.

Work:
- Replace the target ranking's "new-sector" rule with a **priority list of 50,000**: M and K
  dwarfs first, then quiet G/F dwarfs, ≥ 5 sectors, low contamination; re-search a star only
  when a new sector of it is public.
- Keep a **search ledger** (star, sectors, products, pipeline version, result) so work is never
  repeated and the Coverage page is exact.
- Compute platform decision (§9): GitHub-hosted runners' Terms say Actions should not be used for
  "any other activity unrelated to the production, testing, deployment, or publication of the
  software project". A nightly science sweep on hosted runners is a policy risk. Options, in
  order: (1) self-hosted runner(s) on a machine the owner controls (Actions still orchestrates,
  hosted-runner clause does not apply); (2) MAST TIKE (free, 4 cores) for batch runs;
  (3) Kaggle scheduled notebooks (12 h sessions, 4 CPU). Keep hosted runners for CI and the
  small nightly "new sectors" delta only.
- Read FITS from the AWS open-data bucket (`s3://stpubdata/tess/`, anonymous) instead of MAST
  HTTP where possible, to cut fetch time and MAST load.

**Exit tests**
- The 50,000 priority stars are all searched with every public sector by pipeline version ≥ v1,
  recorded in the ledger (coverage page shows 50,000/50,000).
- Per-run failure rate (timeouts + errors) **< 2 %**, retried automatically.
- Throughput measured on the chosen platform over 3 real nights replaces the extrapolation in
  SCIENCE.md §9 (stars/night and CPU-s/star committed).
- A re-run of 500 random stars reproduces the same signals (period within 0.1 %, SNR within 5 %).

## Phase 3: Vetting good enough for a paper (science validation II)

Adopt, don't invent (details in SCIENCE.md §5):
- **LEO-vetter** on every signal that passes the search thresholds (flux-level tests) and on
  candidates (pixel-level tests).
- **Our pixel check** (`skypixels`) on every candidate; keep it as the difference-image stage.
- **TRICERATOPS** FPP/NFPP on every candidate that passes flux + pixel vetting.
- **Gaia DR3** RUWE, non-single-star and variability flags; neighbour dilution.
- Archival **RVs** (ESO HARPS/ESPRESSO) where they exist.
- **Two-person human review** of every candidate before it is called "ready for paper", using
  a written checklist (the dossier order in PRODUCT.md §3).

**Exit tests**
- On a labelled set from ExoFOP (TOIs with TFOPWG disposition **FP/EB vs CP/KP**, ≥ 500 of
  each, Tmag < 13), the automated vetting keeps **≥ 90 % of CP/KP** and rejects **≥ 80 % of FP**.
- Every candidate has LEO-vetter, pixel, TRICERATOPS and Gaia results in its dossier;
  "could not run" is shown and counted.
- Human review: two reviewers agree on ≥ 90 % of a 100-candidate sample (Cohen's κ reported).

## Phase 4: The public monitor and site

Build PRODUCT.md: monitor frames from `hunt/` (`monitor.py`), `POST /monitor/frames`,
`/monitor/now|stream|replay`, star records, search log, coverage, sensitivity, outcomes,
methods; the candidates list and dossier rebuilt on the new evidence.

**Exit tests**
- During a real run, a frame emitted by a runner is visible on the monitor within **10 s**
  (p95), measured over one whole run.
- Turning the API off for 10 minutes mid-run changes **no** search result (frames dropped and
  counted; `results/` identical to a control run).
- Every searched star has a `/stars/[tic]` page; every candidate has a dossier with all sections
  of PRODUCT.md §3 filled or explicitly "not available".
- Honesty lint: zero banned words; every light curve shows observation dates and search date.

## Phase 5: First candidate catalogue and paper

Because ExoFOP requires a published paper for new CTOIs, the first public "submission" is a
paper.

- Freeze pipeline v1.0, archive it on Zenodo (DOI), release the candidate table and all per-star
  search records as open data.
- Invite at least one professional exoplanet astronomer (ideally a TFOP member) to review and
  co-author; they bring follow-up access and ExoFOP experience.
- Write a catalogue paper (method, completeness from Phase 1, false-positive analysis from
  Phase 3, candidate table with ephemerides and vetting results). Target a refereed journal
  that publishes candidate catalogues (AJ, MNRAS, A&A, PASP). The journal choice is the
  co-authors' call.
- Request ExoFOP upload approval
  (`https://exofop.ipac.caltech.edu/tess/pub_candidate_upload_request.php`).

**Exit tests**
- ≥ 10 candidates pass all Phase 3 vetting, both human reviewers, and an external reviewer.
- Paper **accepted** in a refereed journal (URL exists).
- ExoFOP upload approval granted.

## Phase 6: CTOI submission and outcome tracking

- Upload the paper's candidates to ExoFOP with the existing export (`POST /finder/export/ctoi`,
  `flag=newctoi`, `prop_period=0`, all four of period / epoch / depth / duration, paper URL,
  ≤ 120-char notes), one row per candidate, using each TIC's next free `.nn`.
- Poll ExoFOP daily (CTOI and TOI tables) and move each candidate's status: CTOI number →
  promoted to TOI → TFOPWG disposition. Show it on `/outcomes`.

**Exit tests**
- Every uploaded candidate appears in the ExoFOP CTOI table with our tag within 7 days.
- `/outcomes` matches the ExoFOP tables exactly (automated daily diff = 0).
- Goal metric (not a gate): promotion rate of our CTOIs to TOIs, reported each quarter;
  target ≥ 50 %, i.e. in the range of the best independent uploaders.

## Phase 7: Extend into regimes the TESS pipelines miss

Only after Phase 3's vetting holds, extend the search where independent pipelines have found
what SPOC/QLP missed (evidence in SCIENCE.md §2):
- **Faint M dwarfs, Tmag 13–16, with TGLC / TESS-SPOC FFI light curves.** Needs TGLC ingestion
  and a separate sensitivity run; pixel vetting is harder (crowding).
- **Single and duo transits** (already coded: `singles.py`) promoted from "shown" to
  "submittable" with a period-constraint and follow-up plan per object.
- **Multi-year stitching** for long periods in the continuous viewing zones.

**Exit tests**
- For each new regime: injection-recovery grid committed; blind recovery of known TOIs in that
  regime ≥ 70 %; false-alarm rate per 1,000 stars measured and shown on `/sensitivity`.

## Phase 8: Continuous operation

- Runs every night (or continuously if compute allows), new sectors searched within 7 days of
  appearing on MAST, ledger-driven.
- Quarterly pipeline releases with Zenodo DOIs; a candidate's dossier always says which version
  found it.

**Exit test**
- 90 days of unattended operation: ≥ 95 % of nights have a completed run, and every new public
  sector's priority stars are searched within 7 days of release.

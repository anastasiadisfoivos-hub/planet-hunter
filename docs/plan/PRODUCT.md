# PRODUCT: the public site of an open-source planet finder

Content only. No visual design yet (that is a later phase, see [ROADMAP.md](ROADMAP.md)).

## What the site is for

Anyone can watch an open-source search of real telescope data, see every star it has looked at,
and see the candidates it found with all the evidence, so that a professional can judge each
candidate in five minutes and a curious visitor can follow what is going on.

## Rules that apply to every page

1. **Words.** Our finds are *candidates*. Never "discovered", "new planet", "found a planet".
   A candidate becomes a *CTOI* when we submit it, a *TOI* only if the TESS team promotes it, a
   *planet* only when someone else confirms it, and then we say "confirmed by <paper>".
   `api/honesty.py` already enforces the banned words; extend it to the new pages.
2. **Two clocks.** Every light curve, dip and candidate shows **when the telescope took the data**
   (e.g. "observed 2026-07-14 – 2026-08-08, TESS sector 106") *and* **when we searched it**
   (e.g. "searched 2026-09-27 03:41 UTC"). The monitor never implies the data is from tonight.
3. **Every number has its source.** Stellar parameters say "TIC 8.2" or "Gaia DR3"; light curves
   say which product (SPOC 2-min, TESS-SPOC FFI, QLP, TGLC) and version; thresholds link to
   Methods.
4. **Failures are shown.** Rejected signals, retracted candidates, CTOIs the TOI team did not
   promote and TOIs later ruled false positives stay visible with the reason.
5. **Nothing is hidden behind a demo.** Mock data is labelled "demo" (the current `DemoTag`), and
   the monitor never plays mock data as if it were live.

## Site map

| Page | Path | One-line purpose |
|---|---|---|
| Live monitor (home) | `/` | the search happening now, star by star |
| Candidates | `/candidates` | every candidate, ranked, with its status |
| Candidate dossier | `/candidates/[id]` | all evidence for one candidate, in the order a vetter reads it |
| Star record | `/stars/[tic]` | what we searched on this star, what we found or ruled out |
| Search log | `/search-log` | every run, night by night: what ran, how long, what came out |
| Coverage | `/coverage` | which stars have been searched, and how deeply |
| Sensitivity | `/sensitivity` | what the search can and cannot find (injection-recovery) |
| Outcomes | `/outcomes` | scorecard: CTOIs submitted → TOIs → confirmed / false positive |
| Methods | `/methods` | the pipeline, stage by stage, with thresholds and versions |
| About / contribute / cite | `/about` | open source, how to help, how to cite, credits and licences |

Old paths `/finder`, `/finder/[id]`, `/finder/sensitivity` redirect to the new ones.

---

## 1. Live monitor (`/`)

### What the visitor sees

**A. Now searching** (one panel per active runner, default view shows the most recent one; a
compact strip lists all runners):

- Star header: `TIC 123456789`, Tmag, Teff, R★, distance, "M dwarf" / "K dwarf" / etc.,
  constellation, RA/Dec, and why it is in the queue (the `reason` string from `hunt targets`,
  e.g. "M dwarf; 8 sectors; Tmag 11.2; not on any list").
- **Data panel, filling in real time.** As each sector's light curve is downloaded, it appears:
  x = time (BTJD and calendar date), y = normalised flux, one colour band per sector, with the
  sector number and observation dates. This is the real flux (binned for display, ≤ 3,000
  points), in the real order the runner fetches it.
- **Detrend step**: the trend line drawn over the raw flux, then the flattened curve.
- **Search step**: the periodogram (BLS/TLS power vs period) as the search reports its blocks;
  the current best period highlighted. For the dip search, each single dip above SES 7 pops up
  as a marker on the time axis.
- **Vetting step**: for each signal, the checks appear as a list turning pass / fail / could not
  run, each with its one-line reason (this is the `checks` dict, which already has `reason`).
- **Verdict for this star**: "nothing above threshold", "signal at 4.21 d rejected: secondary
  eclipse at phase 0.5 (EB)", or "new candidate → dossier".
- Clocks: "Data taken 2018-08-23 – 2026-08-08 · searching now, started 03:41:07 UTC ·
  step 3 of 5".

**B. Tonight so far**: stars searched / in queue, signals found, where they were rejected
(funnel, live), candidates so far, runners active, run started at, expected end.

**C. Just finished**: a ticker of the last ~30 stars, each one line (TIC, type, result). Clicking
goes to the star record.

**D. Latest candidates**: the 5 newest candidates with folded curve thumbnail and status.

**E. When no run is active** (most of the day if the search runs once a night): the page says so
plainly — "The search is not running right now. Next run starts 02:17 UTC (in 5 h 12 min).
Last run: 2026-09-26 02:17–08:09 UTC, 1,084 stars, 0 candidates." — and offers **"Replay last
night"**, which plays the recorded frames with a permanent banner "Replay of the run on
2026-09-26 at 03:41 UTC, sped up ×20". Replay is never the default when a run is active, and a
replay never shows the "live" marker. (If compute allows continuous runs, see ROADMAP Phase 6,
this state becomes rare.)

### Why this is honest even though the data is weeks old

What is live is **the search**, not the sky. The runner really is processing that star at that
moment; the curve really is being downloaded and flattened; the checks really are running. The
data's own dates are always on screen. The copy says "searching TESS data from sector 106
(observed July–August 2026)", never "watching the sky tonight". TESS products reach the archive
weeks after a sector ends (see [SCIENCE.md §1](SCIENCE.md#1-data)), and the page says so in
Methods.

### Data flow from the nightly run to the site

```
Search runner (GitHub Actions job on a hosted or self-hosted runner, or a TIKE/Kaggle batch;
  │  `hunt run`, one process per star; see SCIENCE.md §9 for which)
  │  at each stage boundary: emit a MonitorFrame (JSON, ≤ 60 kB)
  │    star_started | sector_loaded | detrended | periodogram_block | dip_found
  │    | signal_measured | check_done | star_done | run_started | run_finished
  ▼
POST /monitor/frames   (API, bearer token = repo secret PH_MONITOR_TOKEN;
  │                     fire-and-forget, 2 s timeout, never blocks or fails the search)
  ▼
API (FastAPI, existing)                          Object store (R2 / GitHub artifact)
  ├─ monitor_now: latest frame per runner          full per-star results/<tic>.json,
  ├─ monitor_frames: ring buffer, last 48 h        candidates, merged run summary
  └─ run_log / star_log tables (permanent)         (already produced by hunt merge)
  ▼
GET /monitor/now          → all active runners' latest frame + tonight's counters
GET /monitor/stream       → Server-Sent Events of new frames (fallback: poll /monitor/now every 3 s)
GET /monitor/replay?run=  → recorded frames of a past run, with original timestamps
  ▼
Web (Next.js) monitor page
```

Design choices, and why:

- **Frames are emitted by the search itself**, at stage boundaries, from data the search already
  has in memory (the stitched curve binned to ≤ 3,000 points, the periodogram decimated to
  ≤ 2,000 points, the checks dict). No extra MAST calls; cost is a few kB/s per runner.
- **Push, not pull.** Runners have no inbound address, so they POST. The API only has to accept
  small JSON; it does no science.
- **The monitor must never slow or break the search.** Frames are sent from a background thread
  with a bounded queue; when the API is down the frames are dropped and counted
  (`frames_dropped` in the run summary). The authoritative record is still the per-star
  `results/<tic>.json` in the run artifact.
- **Ring buffer + permanent log.** Frames older than 48 h are deleted (replays keep one
  sampled set per run: the first 200 stars and every candidate star). The `run_log` and
  `star_log` tables are permanent and feed the Search log, Coverage and Star record pages.
- **Hosting note.** A free API host that sleeps when idle (e.g. Render free, "unverified" for
  current limits) wakes on the first POST of a run; the monitor page shows "connecting" until the
  first frame arrives.
- **Contract.** A new `contracts/MonitorFrame.schema.json`, versioned, shared by `hunt` (emitter),
  `api` (store) and `web` (renderer). The emitter is a small module in `hunt/` (`monitor.py`) with
  a no-op default so offline tests and local runs send nothing.

## 2. Candidates (`/candidates`)

- Table, one row per candidate: ID (ours, e.g. `PH-000123` + `TIC 123456789.01`), star type,
  Tmag, period (or "single transit: 40–180 d" / "duo: 47.3 or 23.6 d"), depth, radius (with
  error), number of transits, sectors, score, pixel verdict, statistical FPP (TRICERATOPS),
  **status**, date found, data dates.
- Status ladder (one of): `candidate` → `under review` (internal checks, second vetter) →
  `submitted as CTOI` (with CTOI number and ExoFOP link) → `TOI` (with TOI number) →
  `confirmed (by others)` / `false positive (TFOP)` / `retracted (by us)` / `not promoted`.
  `dismissed` (found later on a list, or failed a later check) is shown under a toggle.
- Filters: status, kind (periodic / duo / single), star type, radius, period, Tmag, pixel verdict,
  sectors, date.
- Default sort: status (open first), then score. The score is explained inline ("what goes into
  the score" link to Methods).
- Download: CSV / JSON of the whole table (open data).

## 3. Candidate dossier (`/candidates/[id]`)

Ordered the way a TFOP vetter reads a DV report.

1. **Summary line**: "Periodic transit-like signal on TIC …, P = 12.3456 ± 0.0004 d, depth
   820 ± 60 ppm (≈ 2.4 R⊕ if on target), 7 transits in 5 sectors, SNR 14.2. Status: candidate."
2. **Status and history**: timeline of every state change with dates (found, pipeline version,
   re-vetted, submitted, CTOI number, TOI number, TFOP notes if any).
3. **The star**: TIC 8.2 + Gaia DR3 parameters (Teff, log g, R★, M★, distance, RUWE,
   non-single-star flag, variability flag), contamination ratio, neighbours within 2.5′
   (with ΔT mag), known lists checked (TOI, CTOI, confirmed, EB catalogue) and the result.
4. **Light curve evidence**:
   - full stitched light curve with each transit marked, sector boundaries, momentum dumps;
   - folded curve and zoom (±3 durations) with the model;
   - each individual transit (small multiples) with its depth and SNR;
   - odd vs even transits; phase 0.5 (secondary eclipse) window;
   - per-sector depth table (dilution consistency);
   - periodogram with aliases marked.
5. **Vetting results**: every check (ours + LEO-vetter tests) as pass / fail / could not run, with
   value, threshold and plain reason. Could-not-run is never shown as pass.
6. **Pixel evidence**: difference image per sector, centroid offset with error ellipse, Gaia
   neighbours with "depth needed to cause this" and whether each is excluded; verdict and
   `on_target_probability` (labelled heuristic).
7. **Statistical validation**: TRICERATOPS FPP and NFPP with the scenario breakdown, and the
   inputs used (no contrast curve unless one exists on ExoFOP). Labelled "not a validation".
8. **Archival checks**: Gaia DR3 RUWE / NSS; any public RVs (ESO archive HARPS/ESPRESSO) with
   what they rule out; ground surveys (e.g. WASP/HATSouth light curves) if public.
9. **What would confirm or kill it**: predicted next transits (with uncertainty) for the next
   90 days, which facilities could see the depth, expected RV semi-amplitude for a range of
   masses.
10. **Provenance**: data products and versions, pipeline version (git SHA), run ID, thresholds,
    date searched. Downloadable: candidate JSON, light curve CSV, the ExoFOP upload row.
11. **Community notes**: see "Community review" below.

## 4. Star record (`/stars/[tic]`)

Every searched star gets one, so "we looked and found nothing" is public too.

- Star parameters, why it was queued, every run that searched it (date, pipeline version,
  sectors used, products).
- The stitched light curve (binned) and the result: signals found and the stage each was
  rejected at, with reasons; dips found and why each was rejected.
- **Detection limit for this star**: "a 2 R⊕ planet with P < 10 d would have been found with
  ~X % probability" from the per-star noise (CDPP) and the sensitivity model.
- Known planets / TOIs on the star (from the lists) and whether we masked them.

## 5. Search log (`/search-log`)

- One row per run: date, start/end, runners, stars attempted / finished / timed out / failed,
  signals, candidates, pipeline version, catalogue snapshot date, frames dropped, run link
  (GitHub Actions run URL).
- Run detail: funnel (existing `/finder/funnel` shape), rejection reasons histogram, slowest
  stars, errors.

## 6. Coverage (`/coverage`)

- Progress to the target list: "37,412 of 50,000 priority stars searched with all available
  sectors" and the queue order rule.
- Coverage by star type (M / K / G / F dwarfs), by Tmag, by number of sectors, and a simple
  all-sky plot (Aitoff or Mollweide, one dot per searched star; a 2D chart, not the old 3D map).
- Re-search rule: a star is searched again when a new sector of it becomes public; show "stars
  waiting for re-search".

## 7. Sensitivity (`/sensitivity`)

- Injection-recovery grids (radius × period) for the whole search and per star type; the
  "detected" vs "recovered" distinction (detected by the search vs survived every cut), which
  today differ a lot at long periods (see ROADMAP Phase 1).
- **Known-planet recovery** (blind test): fraction of known TOIs/planets in the searched sample
  that the pipeline recovers when the known-list masking is turned off.
- What the search cannot do (e.g. P > half the baseline, grazing transits, stars without TIC
  radius, Tmag > limit, crowded fields).

## 8. Outcomes (`/outcomes`)

The credibility page. Counters and a table:
submitted as CTOI · promoted to TOI · TFOP-confirmed / validated by others · ruled false positive
· retracted by us · still pending — each with the list of objects, dates and links. Also the
pipeline's own false-positive rate estimate from Phase 3 of the roadmap.

## 9. Methods (`/methods`)

The public version of [SCIENCE.md](SCIENCE.md): data → detrend → search → vet → cross-match →
rank → submit, with every threshold, the tools and versions used (with citations), what each
stage misses, and a changelog of pipeline versions (each candidate records the version that
found it).

## 10. About (`/about`)

Open source (repo link, licence), how to run the pipeline yourself, how to report a problem with a
candidate, how to cite (Zenodo DOI per release), credits (MAST, TESS mission, SPOC, QLP,
TESS-SPOC, TGLC, Gaia, ExoFOP, tools), data licences.

## Community review (replaces "votes")

The current finder has planet / fake / unsure votes. For a serious finder, a vote count is weak
evidence and can be read as "the public decided". Proposal:

- Keep per-candidate **structured flags** instead of votes: "I see a problem" with a reason chip
  (`looks like EB`, `systematic`, `neighbour`, `known object`, `bad data`, `other` + free text)
  and optional link. Flags are reviewed by maintainers and each gets a public reply.
- Keep the existing anonymous key + rate limit machinery; show flags and replies on the dossier.
- Flags never change a candidate's status automatically.

## API additions this implies

| Route | For |
|---|---|
| `POST /monitor/frames` (token) | runners push frames |
| `GET /monitor/now`, `GET /monitor/stream`, `GET /monitor/replay` | monitor page |
| `GET /runs`, `GET /runs/{id}` | search log |
| `GET /coverage` | coverage page |
| `GET /stars/{tic}` | star record |
| `GET /outcomes` | outcomes page |
| `POST /candidates/{id}/flags`, `GET /candidates/{id}/flags` | community review |
| existing `/finder/*` | candidates, dossier, funnel, sensitivity, CTOI export |

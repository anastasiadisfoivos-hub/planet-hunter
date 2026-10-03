# Critique: home, lab and finder

Method: dual-agent (A: design-review subagent, source plus screenshots, no detector · B: detector plus browser
subagent, isolated from A). Synthesised by the POLISH session, 26 Sep 2026.

Surface: a scratch merge of `origin/skymap` and `origin/homepage` (home is not on skymap yet), run with
`next dev` on :3456. Demo host for the star lab: WASP-18 (TIC 100100827). Finder report:
`tic219345170-01`. Full-page captures of every page at 1440 and 390 are in `current/`.

Not done, by design: the impeccable snapshot under `.impeccable/critique/` (outside this session's fence), and
the skill's closing "ask the user" step. That question is the review this session stops for.

## Scorecard

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 3 | DEMO and paused-source notices are good; the star lab contradicts itself (DEMO header, REAL cards) |
| 2 | Match with the real world | 3 | Plain language throughout; "score", "fake" and Earth/Jupiter unit switching break it |
| 3 | User control and freedom | 2 | No way back to `/` from Lab or Finder; star lab has no back link |
| 4 | Consistency and standards | 2 | Three different top bars, four ways to say "demo", two report systems, the accent used as a data colour |
| 5 | Error prevention | 3 | Disabled actions carry reasons; "vote first, then add a reason" |
| 6 | Recognition rather than recall | 2 | Mini-bars on the candidate list have no legend; hidden-scrollbar lab nav; unlabelled diamonds on the sensitivity chart |
| 7 | Flexibility and efficiency | 2 | Sort and filter exist; no in-page jumps on 4,000 to 6,700px mobile pages |
| 8 | Aesthetic and minimalist design | 3 | Product pages are close; home follows a stock landing rhythm |
| 9 | Error recovery | 2 | Star lab has retry; three 404s on WASP-18's spectra files render as "not connected yet" developer copy |
| 10 | Help and documentation | 3 | Inline explanation everywhere, often excellent |
| | **Total** | **25 / 40** | **Acceptable**: the content is ahead of the chrome |

## Anti-patterns verdict

- **The product pages pass.** Lab, Finder and the candidate report read as bespoke instrument software. The
  charts are real, specific and captioned.
- **Home half fails.** Its sequence is the modal landing template: hero, then a stat row, then a card grid, then
  three doors, then four identical cards, then three value props, then the footer. The hero sky rescues the
  first screen; nothing after it has a point of view.
- **Deterministic scan.** `detect.mjs` over every lab, finder, ui, events and home file (tsx and css) returned
  0 findings, and a planted `border-l-4` and gradient text confirmed the detector was working. The in-page
  overlay flagged 77 items on 7 pages. Most were false positives:
  - 33 low-contrast flags on `/finder/sensitivity`: the detector cannot parse `oklab()` cell backgrounds.
  - 2 `ai-color-palette` flags: 11px legend swatches.
  - Several SVG text-overflow flags.

  The real ones:
  - **line-length**: 22 hits, worst on the star lab, where paragraphs run 1,142px wide at 12px;
  - **cramped padding** inside the shared `Segmented` control: 2px inset;
  - **truncated picture credits** on home: 342px of 438px visible, with no way to read the rest.
- **Measured.**
  - No horizontal overflow at 1440 or 390.
  - 0 contrast failures on essential text. The only sub-4.5 text is disabled controls and two heatmap cells at
    3.8 and 4.2:1.
  - 7 border-radius values in use: 2, 3, 6, 8, 12, 999px and 50%.
  - 6 button styles, at heights of 24, 26, 32 and 40px.
  - 7 to 19 distinct type combinations per page.
  - Every nav link is 32px tall at 390.
  - No box-shadows except five insets used as borders.

## Cross-page (fix these first; every page inherits them)

1. **[P1] There is no shared top navigation.**
   - Home has an absolute, unbordered bar with a 32px gutter: "Planet Hunter · Sky map / Lab / Planet finder".
   - Lab (`components/lab/LabNav.tsx:15-37`) has a sticky bordered bar whose wordmark is "Planet Hunter Lab" and
     links to `/lab`. Its nav lists the four experiments plus "Finder", with "Sky map" as an outlined button.
   - Finder (`components/finder/FinderNav.tsx:8-35`) has "Planet Hunter Finder" → `/finder`, with "Candidates /
     What it can find / Lab" plus the same button.
   - Nothing outside home links to `/`, and one destination has three names ("Planet finder", "Finder",
     "Candidates").
   - At 390 the Lab and Finder bars wrap to 93px, and the Lab nav hides two links behind a hidden scrollbar.
   - Fix: one global bar and one naming, with section sub-navigation moved into the page header. See
     DIRECTION.md, Top navigation.
2. **[P1] The containers don't share a grid.** Home is 1200px max with 32px padding, so content starts at
   x=152, while its bar sits at x=32. Lab and Finder are 1240px with 24px padding, so the wordmark sits 100px
   left of the content edge. h2 is 24px on home and 20px elsewhere. Fix: one container (1200 + margins) that the
   top bar also uses.
3. **[P1] Four ways to say "demo".** There is the dashed `DEMO DATA` tag, a bordered ⓘ help box (Hubble, star
   lab), a caption starting "Demo: …" (Finder), and plain "Demo data" text (`SpectraCards.tsx:102`). DESIGN.md
   asks for one visible tag. Fix: one tag component plus one caption sentence, placed where the data is.
4. **[P2] The accent is used as a data colour.** It appears in:
   - the Hubble fit line and handle (`Hubble.tsx:121,127`);
   - the transit ticks and playhead (`HearStar.tsx:216-222`);
   - the model curve (`MeasureCard.tsx:63`) and the Kepler guess orbit (`KeplerCard.tsx:56`);
   - the element bars (`Fingerprints.tsx:402`);
   - the finder predicted-dip ticks (`finder.module.css:738, 922`);
   - "Your planet" text (`star.module.css:192, 241`);
   - home's decorative honest-list rules (`home.module.css:637`).

   Fix (DIRECTION.md, Charts): the user's own model or guess is a dashed `--ink` line, the measured or pipeline
   answer is solid `--ink`, predicted ticks are `--ink`, and `--accent` stays on selection and focus.
5. **[P2] Event-category colours are reused as status.** The Finder verdict pills use green (solar system) for
   "On target", yellow (Sun) for "Possible neighbour" and `--supernova` for "Off target"
   (`finder.module.css:109-120`), with raw `rgb()` tints. Green means "solar system" on the map. Fix: status
   carries a glyph plus a word in neutral ink; only a blocking or failing state gets `--supernova`.
6. **[P2] Two systems for long pages.** The star lab nests three levels deep (section panel > planet card > chip
   card), while the Finder report uses hairlines. Home mixes hairlines and card grids. Fix: ruled sections
   everywhere, and cards only for things you click that carry a picture.
7. **[P2] The type scale is loose.** Nine sizes are defined (11 to 32) and the pages add 21px outliers plus
   two 0.42px mono elements on the report (probably an sr-only style leaking). Mono relative times render as
   "2  d  ago" with wide gaps. Fix: DIRECTION.md's eight-step scale, with relative times in sans.
8. **[P2] Word bans are broken.**
   - "Score", "Ranked by score" and "each failed check takes points off" (`finder.ts:65`) break DESIGN.md's "no
     points or scores anywhere".
   - "Looks like a fake" (`VoteBox.tsx:11`) and "We hide fake planets" (`Sensitivity.tsx:53`) are casual next to
     "candidate".
   - "each locked one says … what would unlock it" (`StarLab.tsx:76`) is game language, and nothing is locked.
9. **[P3] Tap targets.** Every nav link is 32px tall at 390. Segmented options are 24 to 26px. The vote buttons
   and reason chips are 40px, 4px short. DESIGN.md already says 44px on coarse pointers; the segmented control
   and nav ignore it.

---

## /lab/star/[tic] (WASP-18, demo host): worst

- **[P1] DEMO and REAL contradict each other.** The header tags WASP-18 "DEMO DATA" while Thermometer,
  Hear it, Measure and Kepler each carry "REAL DATA". Users lose trust exactly where they're asked to give it.
  Fix: page-level tag only when every card is demo; otherwise per card.
- **[P1] Developer copy in the UI:** "Real Gaia DR3 XP spectra arrive with the SPECTRA files", "The star lab
  service isn't connected yet", "Made-up abundances for building the UI" (`StarLab.tsx:80`,
  `build-mocks.mjs:137`). Three data files 404 on every load (`/data/spectra/stars/100100827.abundances.json`,
  `.gaia_xp.json`, `/data/spectra/planets/wasp-18-b.atmosphere.json`).
- **[P2] Cards nested three deep.** "Its planets' air" is a 276px card alone inside a 1,190px panel. The Kepler
  chart leaves about 60% of its 776px panel empty. The Thermometer right column has a 110px dead gap.
- **[P2] Line length.** Paragraphs have `max-width: none` and run 668 to 1,142px wide, 12 to 14px (detector ×8).
- **[P2] At 390:**
  - the spectrum chart's "UV" and "VISIBLE" labels collide;
  - "WASP-18" overlaps "Sun" on the HR diagram;
  - the element bars shrink to about 100px;
  - "Fly to it" wraps onto its own row;
  - the page is 6,721px tall with no in-page jumps.
- **[P2] Six experiments at full depth on one scroll.** Offer a sticky in-page index, not six full panels.
- **[P3]** The "R☉" glyph renders tiny. Speed and "Raw / Folded" controls are 26px tall.
- **Working:** Measure its planet is a superb loop: sliders, then "gap to data", then the pipeline's answer, then
  the archive's. Every derived number is sourced.

## /finder/[id] (candidate report)

- **[P1] The crowd tally shows before the user votes** ("41 / 6 / 9", "56 people have voted"). That anchors the
  one judgement the page asks for. Fix: counts after voting (mock does this).
- **[P1] On mobile the vote sits at y≈5,700 of 6,137px, after Priority/Score.** On desktop the rail ends at
  y≈546 and leaves 2,400px of empty column. Fix: at ≤1023px, place the vote right after the facts; sticky rail on
  desktop (mock does this).
- **[P2] Dead buttons are the loudest controls in the header.** "Open star lab" and "Fly to it" render as dashed
  ink-faint boxes (`Report.tsx:48-55`), 4.49:1, with `tabIndex=-1`, explained in a caption below. Fix: hide them
  and keep the one-line note.
- **[P2] "On the target 95%" has no basis** (`Pixels.tsx:147-149`). DESIGN.md wants "95%, from the pixel check".
- **[P2] Units switch.** The header says "4.4 × Earth"; the Planet-sized check says "0.39 Jupiter radii" and
  "0.39 RJ". Pick Earth radii for sub-Jovian candidates.
- **[P2] The demo pixel images say sector 104 and "copied from WASP-18"** while the page says sectors 81 and 82.
  It is disclosed, but at 12px under the images. Put "Demo: WASP-18's pixels, not this star" in the image caption
  itself.
- **[P3]** Each check has a green icon plus "PASSED" plus "6 PASSED" in the heading, three signals for one
  fact. Known lists is four identical cards that all say "Not on the list"; one ruled row reads faster. The
  score-part swatches in `--ink-muted` and `--ink-faint` are nearly indistinguishable. A 21px heading exists
  only here.
- **Working:**
  - the 8-fact grid with sub-notes (BTJD and BJD, ppm);
  - "It orders the list; it is not the chance this is a planet";
  - the folded and whole light curves.

## /finder (candidate list)

- **[P1] "Ranked by score" and the "Score" column** (word ban).
- **[P2] The mini-bars under score and votes have no legend.** The vote bar is white/orange/grey and its meaning
  exists only in `aria-label` (`CandidateList.tsx:58`).
- **[P2] The filter bar has seven controls** (2 selects, 4 pixel-check toggles, a votes toggle). The toggles
  look like the report's vote-reason chips but behave differently. "14 of 14" floats at the far right, off the
  baseline.
- **[P2] At 390:**
  - 14 cards each repeat "SCORE PERIOD SIZE VOTES" labels;
  - "found 18 Sep" and "needs votes" are dropped;
  - "0.76× Jupiter" wraps;
  - row links are 21px tall.
- **Working:** The funnel ("48,213 stars searched → 14 to review", with its log-scale note) is honest and
  specific. The pixel-check pills pair an icon with a word.

## / (home)

- **[P2] Template rhythm** (see verdict). Six identical picture cards, then four identical star cards, then
  three value props.
- **[P2] The Sky map door is the weakest image on the page:** about 400px of black with a small ellipse,
  advertising the flagship. The door art sits in a black well inside a raised card, which is a nested surface.
- **[P2] "100%, machine guess"** appears on the nova and the TDE. It undermines "Machine guesses are labelled".
  Show what the machine's score means, or state the basis differently.
- **[P2] A hard seam at y=640 where the `#000` hero meets the `#09090B` body.** It reads as two pages stitched
  together. Fix: one black canvas (DIRECTION.md, Surfaces).
- **[P3]**
  - The archive caveat "Archive photo from years before. The event itself is not in it." repeats on every card.
  - Credits truncate to "…" with no way to expand.
  - Mono "2 d ago" has wide gaps.
  - At 390 the nav has an 8px right gutter against a 16px left one (`home.module.css:704`), and the DEMO DATA
    tag wraps alone.
- **Working:**
  - The hero sky plus star search, and its hint ("Stars with known planets open in the Lab. Anything else is
    looked up on the sky map").
  - Paused sources stated exactly as DESIGN.md asks.

## /lab (index)

- **[P2] Star labs are missing from the index.** "Four small experiments", while the star page says "Six
  experiments on this one star". Star labs are reachable only from home or the map, and "Finder" sits among the
  experiments in the nav.
- **[P2] At 390 the experiment nav scrolls sideways with a hidden scrollbar** (`lab.module.css:765-771`).
  "Chemical fingerprints" and "Finder" are cut off with no affordance.
- **[P3]** The footer note explaining DEMO tags is 12px muted text, far from the tags.
- **Working:** Rows with a real thumbnail of each chart and REAL/DEMO tags: honest and scannable.

## /lab/hubble

- **[P2] The first screen states a wrong fact at display size:** the line starts at 45 km/s/Mpc and shows
  "Age of the universe, roughly 21.7 billion years". Label it "your line's answer" until it is fitted.
- **[P2] Two controls for one value:** the drag handle and the slider. The handle sits in the bottom-right corner
  and is easy to miss.
- **[P3]** Segmented control has a 2px inset (detector) and is 26px tall. One uppercase SVG axis title.
- **Working:** The "As measured / Distance and speed" toggle and the long-form explanation.

## /finder/sensitivity: best page

- **[P2] Candidate diamonds cover the cell percentages** (97, 100, 91, 18, 6). They aren't links, have no
  hover identity, and the filled versus hollow styles are unexplained. The diamond is also the solar-system glyph
  on the map.
- **[P2] Demo candidates plot in 1 to 3% recovery cells.** A researcher reads that as implausible or remarkable.
  The "30" x-tick is clipped at 390. Two cells ("38", "34") are 3.8 and 4.2:1 at 10 to 11px.
- **Working:** A true instrument chart with numbers in the cells. "Why long orbits drop off" is exemplary copy.

---

## Personas

- **Curious first-timer.**
  - Lands on /lab from home, then can't get back: the wordmark reloads /lab.
  - Reads "the universe is 21.7 billion years old" before touching the line.
  - Sees DEMO next to REAL on WASP-18 and stops trusting anything.
- **Researcher.**
  - Vote counts shown first bias the vote.
  - "Looks like a fake" is too casual.
  - Sector 104 pixels sit on a sector 81 and 82 candidate.
  - "95%" has no basis.
  - No deep links to report sections, and no way to copy a TIC from the list.
- **Keyboard or screen-reader user.**
  - The vote bar's meaning is only in `aria-label`, so sighted keyboard users get nothing.
  - Dead ghost buttons are visible but removed from the tab order.
  - Two lab links are hidden behind a scroller at 390.
  - The sensitivity diamonds aren't focusable.

## Cognitive load

Three checklist failures, which is moderate:
- **Minimal choices:** the Finder filters (7) and the star lab (6 experiments at once).
- **Progressive disclosure:** the star lab opens everything at full depth.
- **Working memory:** Earth-to-Jupiter unit switching, legend-less mini-bars, and a vote 5,000px from its
  evidence on mobile.

## Questions this review leaves for the owner

1. Should anyone see the crowd's verdict before giving their own? (Recommended: no.)
2. Is "score" needed at all? DIRECTION.md proposes "priority", with the four parts shown.
3. Is the star lab a scroll of six panels or an instrument bench with one experiment in focus and an index?
4. What is the one thing a first visitor should do on home: search a star, open the sky, or read this week?

# MONITOR-UI: proof

The planet finder rebuilt around one idea: a **monitor** that streams the searched star's real TESS light curve across
the page as one ink line on chart-recorder paper, and marks each dip in the margin as the pen reaches it.

* Direction and rules: [`web/DESIGN.md`](../../DESIGN.md) (authoritative).
* References: [`refs/README.md`](refs/README.md) (6 Awwwards sites, 2 real instruments, with screenshots).
* Mock data, all real: [`public/data/monitor/README.md`](../../public/data/monitor/README.md).
* The monitor moving: [`monitor.gif`](monitor.gif) (10 s at 720 px, 10 fps: two known dips being marked, then the paper
  advancing to the next star).

## Screenshots (`screens/`)

| page | 1440 | 390 |
| --- | --- | --- |
| Monitor `/` (mid-stream) | `monitor-1440.png` | `monitor-390.png` |
| Monitor, night theme | `monitor-1440-dark.png` | `monitor-390-dark.png` |
| Monitor, reduced motion (still curve) | `monitor-1440-reduced-motion.png` | |
| Candidates `/candidates` | `candidates-1440.png` | `candidates-390.png` |
| Dossier, TOI-7303.01 stand-in | `candidates-tic415739607-01-1440.png` | `candidates-tic415739607-01-390.png` |
| Dossier, TOI-4257.01 stand-in (real pixel check: off target) | `candidates-tic75208638-01-1440.png` | `candidates-tic75208638-01-390.png` |
| Log `/log` | `log-1440.png` | `log-390.png` |
| Sensitivity `/sensitivity` | `sensitivity-1440.png` | `sensitivity-390.png` |
| Methods `/methods` | `methods-1440.png` | `methods-390.png` |

Full-page screenshots show the paper's grain only on the first screen: the grain is a fixed layer, as DESIGN.md asks.

## Checks run

* `npm test`: 138 tests (1 more, the live redirect test, runs with `MONITOR_BASE` set). New:
  `tests/monitor/client.test.ts` (replay order and prefetch, live polling, retries, abort),
  `tests/monitor/format.test.ts` (the "Live" / "Replay of the 26 Sep 2026 search" label, data dates, units),
  `tests/monitor/trace.test.ts` (tape, gaps, dips only where there is data, speed profile, phases, flux scale),
  `tests/monitor/routes.test.ts` + `redirects.http.test.ts` (every /finder URL answers 308 with the new place, query kept).
* `npm run lint`, `npm run typecheck`, `next build`: clean.
* In a browser (Playwright, production build): the monitor runs at 60 fps at 1440 and 390; the canvas is frozen while
  the tab is hidden and resumes; Pause holds it; reduced motion shows the whole curve still, all notes listed, no Pause
  button, "Next star" works; no horizontal scroll on any page at 390; no console errors.

## Phase 5: /impeccable audit

Scores before the fixes below: accessibility 3, performance 3, responsive 3, theming 4, anti-patterns 3 (16/20).
After: 4, 3, 4, 4, 4 (19/20). Performance stays at 3 because each replayed star is a 100 to 200 kB JSON file; the API
can send it binned coarser if needed.

### Fixed (DESIGN.md agrees)

| finding | fix |
| --- | --- |
| Table heads and the "Stand-in" label were 4.42:1 on `--paper-2` (WCAG AA) | `--ink-3` #6A6459 → #645E53, `--pen` #B8321A → #AE2F18: now at least 4.8:1 on both papers |
| Sensitivity cells flipped text colour at 55% density; cells near the flip fell under 3:1, and the "of N" line was dimmed to 80% | Ink density capped at 40% and text always ink: at least 5.0:1 measured on the rendered cell |
| Tap targets under 44px on phones: wordmark, footer links, the dossier's back link and ExoFOP link, methods contents, log filters, vote reasons | 44px on coarse pointers (standalone links, filters, chips); inline links in prose stay inline (WCAG 2.5.8 exemption) |
| Side stripe (2px left border) on the methods placeholder: an absolute ban | A full 1px dashed rule |
| A decorative notch between funnel steps | Removed |
| No way to jump past the top bar | "Skip to the page" link, shown on focus |
| The dossier plot's x-axis title collided with tick labels at 390 | Moved to the plot's top edge |
| Detector (`detect.mjs`) over all new files | No findings |

### Rejected (DESIGN.md wins)

| impeccable says | why not here |
| --- | --- |
| Warm near-white "paper" grounds, and a token called `--paper`, are the 2026 AI default | The ground is literally recorder paper: the product's one idea is a chart recorder, and the trace, grid and pen only make sense on it. The night theme is near-black ink-paper. The name stays because it is what it is. |
| Product register: one family, fixed rem scale | This is a public, editorial instrument, not a logged-in tool. DESIGN.md sets Newsreader for words and Martian Mono for numbers, and a fluid display size for the star's name. |
| Use OKLCH tokens | DESIGN.md keeps hex tokens; every pair's contrast is computed and written in the colour table. |
| Numbered section markers are scaffolding | The methods page is a real sequence (the order the search runs), which impeccable itself allows; no other page numbers its sections. |
| Uppercase tracked kickers are an AI tell | Mono caps label data only (scales, units, table heads). The one kicker, "Planet candidate, not a confirmed planet" on the dossier, is there for the honesty rule. |
| A page with no entrance motion | DESIGN.md: no entry animations on scroll; only the trace moves. |

Left as is (P3): hunt's own check sentences say "R_sun"; they are shown verbatim because they are the search's words.

## v2: the owner's feedback pass (27 Sep 2026)

Screenshots in [`screens-v2/`](screens-v2/): monitor, log, candidates and the TOI-4257.01 dossier at 1440, 1920 and 390,
plus the monitor and log at night (1440 and 390).

| asked | done |
| --- | --- |
| Bolder and bigger | Body 18→21px, labels 12px, numbers 15px Martian Mono 500; Newsreader 500 for headings, 600 for names; display up to 96px; section titles at `--t-h1`; log rows at least 84px. |
| Use the whole screen | No centred column anywhere: `--gutter: clamp(24px, 4vw, 80px)` and full-width grids; the sky map and the star table run edge to edge. (The retired pages' global `.wrap` max-width is reset under `.site`.) |
| Colour that means something | Each star in its blackbody colour from its TIC temperature (`starColour.ts`, Mitchell Charity's table): log rows, sky dots, candidate rows, the dossier and the rule under the monitor's star name, always with the key. Night is deep space ink `#0B0C18` under two faint radial glows. Pen and catalogue blue unchanged. |
| SVG art | `Glyphs.tsx`: star type (M/K/G/F dwarf, subgiant, giant), a planet crossing its star, TESS, and an empty trace for "no candidate yet"; one 1.25px stroke. |
| All-sky map | Mollweide, RA 0h centred and increasing to the left, graticule, Milky Way band with ±10° edges, the ecliptic, and TESS's CCD footprints for sectors 104 to 106 from tess-point (`components/monitor/data/build_sectors.py`). |
| Empty sparklines | Cause: only the 19 replayed stars had a stored curve. Now every searched star has a 180-point trace (`sparks.json`, lowest point per bin so dips survive): 205 of 205. A star without one would say "no curve stored". |
| 205/309 vs 200/297 | Two sources: the monitor counted the log (and known planets masked before the search), the candidates page read the sweep file. Now both read `/monitor/stats`: 205 stars, 307 signals the search found, one funnel over the same stars. `tests/monitor/data.test.ts` holds it. |
| Margin notes flush left | Canvas text (notes, dates, flux scale) aligns to the same gutter as the page. |

### /impeccable audit, v2

Detector: no findings. Browser checks on all six pages, light and night, 1440 and 390: every text pair at least 4.5:1
against its real background (night palette: ink 16.2, ink-2 9.2, ink-3 5.8, pen 7.3, blue 9.6 on `#0B0C18`), one h1,
no skipped heading levels, every control named, 44px targets on touch, no horizontal scroll. Fixed on the way: the
phone nav cut off "Methods" at the bigger size, the star name and dossier title wrapped on phones, mono numbers
could wrap ("9 598 / K"), plot captions and sub-lines were still 14px, declination labels sat under dots, and a
decorative glyph had an empty accessible name. The monitor still runs at 60 fps at 1920.

Rejected, DESIGN.md wins: the skill's ban on hand-drawn SVG (the owner asked for it and it is the recorder's own line),
its call for photographs (the data is the image), and its discouragement of a serif and a warm paper ground (the
product is a paper chart recorder); impeccable's "paper ground is an AI default" stands rejected as before.

## v3: white sheet, bold type, icons that explain (27 Sep 2026)

Screenshots in [`screens-v3/`](screens-v3/): monitor, candidates, the TOI-4257.01 dossier, log and methods at 1440, 1920
and 390, plus the monitor at night (1440, 390). DESIGN.md was rewritten first (v3) and governs this pass.

* **Day by default** on `#FAFAF7` with black ink, whatever the operating system prefers; **Night** is a switch in the
  top bar, remembered in this browser and applied before first paint (`html[data-theme="night"]`, flat `#0C0D12`,
  no glows).
* **Type**: **Archivo** (Omnibus-Type, SIL OFL 1.1), headings 800 at width 112, names 700, body 500; **Martian Mono**
  (Evil Martians, SIL OFL 1.1) 500 for numbers and edge labels. Newsreader is gone.
* **Hand-coded look**: square corners everywhere, 2px ink rules under the top bar, page heads and table heads, end
  ticks on the head rule, hairlines between rows, asymmetric 5/7 heads. Removed: grain, glows, blur, shadows,
  rounded boxes.
* **Navigation**: each section is an icon and one word; on phones the four icons sit in one row under the name.
* **Explainer strip** on every screen (`components/shell/explain.ts`): 3 or 4 icon + two-word keys, each a toggletip
  with one sentence (Escape, a second tap or a tap elsewhere closes it). The prose that used to open each page is
  gone; long explanations belong in /methods.
* **Icons**: 20 new hand-drawn icons in the glyph set (one 1.5 stroke on 24px), used in the nav, the strips, the
  methods steps, the mode box and the Day/Night switch.
* **Kept**: the streaming trace, star temperature colours, the red pen, catalogue blue, the replay label, data dates,
  "candidate" not "discovered", counts after voting, reduced motion.

Checks: 143 tests (new `explain.test.ts` holds the strip rules) plus the live redirect test; lint, typecheck and
`next build` clean; the monitor runs at 61 fps; Day stays the default when the OS is dark; Night is remembered after
a reload.

/impeccable audit, v3: detector clean; on all six pages, day and night, 1440 and 390: AA contrast everywhere, one
h1, no skipped headings, every control named, no horizontal scroll, 44px touch targets. Fixed during the pass: the
Day/Night switch had no accessible name on phones (its word is hidden there) and was 40px tall; a 6px left border on
the honesty line (a side stripe, banned); the monitor's blur crossfade and a shadow on the star rule; two page titles
that wrapped ("TIC" is now a mono kicker above the number); explainer tips that ran to two sentences.
Rejected, DESIGN.md wins: the skill's ban on hand-drawn SVG icons (the owner asked for them, and one hand-drawn set
matches the trace), its call for photographs, and its preference for an icon library.
`monitor.gif` still shows the v1 look; the screenshots are current.

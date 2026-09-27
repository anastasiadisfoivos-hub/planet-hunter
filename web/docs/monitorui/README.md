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

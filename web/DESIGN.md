# Planet Hunter: DESIGN.md

This file is authoritative for everything under `web/`. Where a skill, a library default or a habit disagrees
with it, this file wins, and the work says so.

Owned by the MONITOR-UI session. References and the reasoning behind them: `docs/monitorui/refs/README.md`.

## Direction: the chart recorder

Planet Hunter is a planet finder and nothing else. Its home is a **monitor**: the star being searched streams its
real TESS light curve across the page as one continuous ink line on warm recorder paper, and when the search finds
a dip, the observer's red pen marks it in the margin above the trace. Everything else on the site is the paper
that comes off that recorder: the log (one row per star, like a helicorder drum), the candidates (a dossier per
signal) and the methods (the lab notebook).

Five rules that make it feel made by a person:

1. **One line is the hero.** No hero photograph, no 3D, no gradient. The line is real data, and it is labelled
   like an instrument trace: the star, the sector and the date sit on the paper next to it.
2. **Paper, ink and one pen.** A warm paper ground, near-black ink for data and words, and one vermilion pen for the
   things the search found. Known objects are written in catalogue blue. No other colours.
3. **Edges carry the numbers.** Small mono labels on the edges of every chart and page (time, units, state), the way
   a chart recorder prints its scale. Words are in a serif with a voice.
4. **State is said in words.** "Replay" or "Live", "observed 2 to 28 Aug 2026 by TESS", "candidate", "rejected:
   reason". Motion never stands in for a state.
5. **Nothing loops for decoration.** Only the trace moves, and only while it is drawing a star.

Not a game: no scores, points, streaks, levels, badges, "you found", or celebration.

## Colour

Tokens live in `styles/tokens.css` on `.site` (the new shell). Components use tokens, never raw hex. Two themes: paper
(default) and night (under `prefers-color-scheme: dark`). All text pairs meet WCAG AA on `--paper`.

| token | paper | night | use |
| --- | --- | --- | --- |
| `--paper` | `#EDE8DC` | `#12110E` | page ground: recorder paper |
| `--paper-2` | `#E5DFD1` | `#1A1915` | a sheet lying on the paper: dossier panels, table heads |
| `--grid` | ink at 7% | ink at 8% | the chart grid (minor divisions) |
| `--grid-strong` | ink at 15% | ink at 16% | major divisions, rules between rows |
| `--ink` | `#1C1A16` (14.2:1) | `#ECE6D8` | the trace, headings, body text |
| `--ink-2` | `#4F4A41` (7.2:1) | `#B3AC9D` | secondary text |
| `--ink-3` | `#6A6459` (4.8:1) | `#8E887B` | edge labels and scale numbers only |
| `--pen` | `#B8321A` (4.9:1) | `#FF7458` | **the observer's pen**: dips the search found, candidates, focus rings, the live dot. Never decoration. |
| `--known` | `#2C5A86` (5.9:1) | `#8DB4DC` | objects already on a catalogue: known planets, TOIs, binaries |
| `--rejected` | `--ink-3` | `--ink-3` | dips the checks turned down: drawn hollow, never red |

- Meaning is never colour alone. A found dip is a filled pen tick; a known one is a blue tick with a small bar; a
  rejected one is a hollow ink tick. Each carries a word ("candidate", "known", "rejected").
- The paper carries a very faint grain (a fixed, `pointer-events: none` SVG noise layer at 3.5% on paper, 5% at
  night). It is off in `forced-colors`.

## Type

Two families, both under the **SIL Open Font License 1.1**, loaded with `next/font/google` in `app/layout.tsx`
(self-hosted at build time, no runtime request to Google):

- **Newsreader** (Production Type, OFL 1.1): every word meant to be read. Headings, star names, prose, the
  candidate dossier. Variable, with optical sizes: large headings use its display cut, body its text cut.
  Headings sit at weight 400 to 500, never bold-black; italics are for the pen's voice ("rejected: …").
- **Martian Mono** (Evil Martians, OFL 1.1): every number and every edge label. Scales, TIC numbers, dates, ppm,
  the tally. Set at width 87 ("condensed") for labels, 100 for numbers in tables. Uppercase with +0.06em tracking
  for labels only; numbers stay mixed case with `tabular-nums`.

No other families. Banned here: Geist, Inter, Helvetica, Arial, Roboto, Space Grotesk. System UI fonts only as
fallbacks.

Scale (fluid, `clamp()`), in `styles/tokens.css`:

| token | size | use |
| --- | --- | --- |
| `--t-display` | 44 → 88px, line 0.98, tracking -0.02em | the star's name on the monitor, page titles |
| `--t-h2` | 26 → 34px, line 1.1 | section heads in the dossier and methods |
| `--t-body` | 17 → 19px, line 1.5, measure 62ch | prose |
| `--t-small` | 15px, line 1.45 | captions, row text |
| `--t-label` | 11px Martian Mono, uppercase, +0.06em | edge labels |
| `--t-num` | 13px Martian Mono, tabular | numbers in rows and readouts |

### Numbers and units

- A dip's depth in ppm under 1000, in % above ("1 840 ppm", "0.79%"). Thin space as the thousands separator.
- Periods: hours under a day, days otherwise ("17.2 h", "2.34 d"). Never scientific notation.
- Temperatures in K, radii in solar radii ("0.76 R☉"), magnitudes as "T 10.8".
- Dates: "2 to 28 Aug 2026"; with years apart, "Jul 2023 to Jun 2026, 3 sectors". Times are UTC and say so.

## Space and grid

- 4px base. Steps: 4, 8, 12, 16, 24, 32, 48, 72, 112 (`--s-1` … `--s-9`).
- The page grid is the chart grid: a 12-column layout with a **left margin column** (the notebook margin, 1 column
  on desktop, gone on phones) where kind labels and dates sit. Section rhythm is 72px desktop, 48px phone.
- Side gutter: 32px desktop, 16px phone. Max content width 1320px; the monitor is full-bleed.
- Corners are square. The only radius is 2px on buttons and inputs. No cards with shadows; a sheet is a
  `--paper-2` fill with a `--grid-strong` rule at its top, like a page laid on a desk.

## The monitor (the signature)

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ Planet Hunter   Monitor · Candidates · Log · Methods               ● REPLAY      │
│                                                                                  │
│ TIC 415739607                              (margin lane: pen ticks + labels)     │
│ a K dwarf, T 10.8 · 4 439 K · 0.76 R☉     ▼ dip · 2.34 d · 2 950 ppm · known     │
│ observed 18 Jul to 12 Aug 2026 by TESS ───────────────────────────────────────── │
│                                                                                  │
│ ~~~~~~~~~~~~~~~~~~~~~~~~~\_/~~~~~~~~~~~~~~~~~~~~~~~~~~~\_/~~~~~~~~~~●             │
│                                                                    ↑ pen head    │
│ ────┼──────────┼──────────┼──────────┼──────────┼─────── 20 Jul · sector 82 ──── │
│                                                                                  │
│ 214 stars searched · 311 signals · 0 new candidates        next: TIC 113233475   │
└──────────────────────────────────────────────────────────────────────────────────┘
```

- **Paper**: a full-bleed canvas (`100dvh` minus the top bar, at least 520px) with ECG-style divisions: minor
  every 1 day of data, major every 5 days, in `--grid` / `--grid-strong`. The grid scrolls with the data, so the
  paper moves under a fixed pen.
- **Trace**: one 1.5px `--ink` line (2px at night for glow-free legibility), drawn left to right. The **pen head**
  sits at 72% of the width; data to its left has been drawn, the paper to its right is blank. A small filled
  circle (6px) in `--ink` marks the pen. Sector gaps are drawn as a break in the line with the sector number
  printed in the gap, never bridged.
- **Speed**: about 2.2 days of data per second of wall time (a 27-day sector in about 12 s), eased in at the start of
  a star and out at the end. The trace draws at 60 fps on a 2D canvas.
- **Detections**: when the pen reaches the middle of a dip the search found, the pen writes a tick in the margin
  lane above the trace (ECG annotation style: a 1px vertical rule down to the trace at that time) and a label in
  mono: kind, period, depth, outcome. For a periodic signal, every later dip of that period gets a smaller tick as
  the pen reaches it. Candidate and known dips are redrawn in their colour with a wash across the band (pen wash
  for candidates, grid tint for known); rejected dips keep the ink line and get a hollow tick, and only their first
  dip a dashed rule. Ticks fade in over 160ms, never bounce. The notes under the monitor list each signal as the
  pen reaches it, with hunt's reason.
- **Handover**: at the end of a star the trace finishes, the readout holds for 1.8 s, then the paper advances (the
  finished trace slides off to the left in 900ms, `--ease-in-out`) and the grid runs on without a jump. Only then does
  the header change: the next star's name crossfades in over 240ms with a 2px blur to mask the swap. A skip the
  viewer asks for ("Next star", or →) advances in 240ms: keyboard actions are never slow.
- **Notes stay readable**: each signal's note (outcome, period, depth) sits by its first dip, and once that dip has
  scrolled away it stays pinned at the lane's left edge while the signal's later dips are on screen. Rules and ticks
  pass behind notes, which are knocked out of the paper.
- **Gaps**: where TESS has no data the pen lifts: no dot, no line, only the stylus rule moving over blank paper.
- **Mode**: top right of the monitor, in mono caps, above Pause and Next star. `● LIVE` (pen dot) when the API streams the star being searched now;
  `REPLAY` with the recording date ("replay of the 26 Sep 2026 search") otherwise. Mock data is always replay.
- **Tally**: bottom left, one mono line: stars searched, signals, candidates. It updates when a star finishes,
  with no counting animation.
- **Reduced motion**: no streaming. The whole curve is drawn still, every detection tick is shown at once, and
  the star changes only when the viewer presses "Next star". **Hidden tab**: the animation pauses and resumes where
  it was.
- **Pointer**: hovering the drawn part shows a thin vertical cursor with time and flux at that point.
  Keyboard: the monitor region is focusable; Space pauses/resumes, → skips to the next star.
- **Phone**: the canvas is 62dvh; the margin labels collapse to ticks plus a list under the canvas.

## Other pages

- **/candidates**: a table on paper. One row per candidate: TIC, period, depth, size, checks passed, pixel check,
  vetting verdict. Row hover draws a rule under the row in ink. The page header states the honest count first
  ("The search has found no new candidate yet. These are stand-ins: real TESS Objects of Interest.").
- **/candidates/[id]**, the dossier: a two-column sheet. Left, in order: the dip (folded and zoomed traces, drawn
  with the monitor's line), the checks (each in a sentence), the pixel check, vetting (LEO, TRICERATOPS, Gaia,
  variability), and votes. Right margin: the star's facts and the data dates. Votes: counts appear only after the
  viewer votes.
- **/log**: the helicorder. Every star searched is one row, newest at top: time searched, TIC, sectors, a tiny
  sparkline of its curve if we have it (else a flat rule), and its outcome word. Above it, the **coverage**: a
  flat all-sky map (equirectangular RA/Dec, RA increasing to the left, like looking up) with one dot per star
  searched, filled pen if it had a candidate, blue if known, hollow ink otherwise.
- **/sensitivity**: the injection-recovery grid as a table of ink densities on paper, with numbers in each cell.
- **/methods**: the notebook. Section heads with numbered margin labels; the text arrives from session PLAN.
  Until then each section says "Written by the methods session; not yet here." in `--ink-3`.
- `/finder`, `/finder/[id]`, `/finder/sensitivity` redirect to `/candidates`, `/candidates/[id]`, `/sensitivity`.

## Components

- **Top bar**: 56px, on paper, a `--grid-strong` rule below. Left: "Planet Hunter" set in Newsreader italic 20px.
  Then Monitor, Candidates, Log, Methods in Newsreader 17px, `--ink-2`, current page in `--ink` with a 2px pen
  underline. Phone: the links stay in one scrollable row, no hamburger.
- **Buttons**: text in Martian Mono 12px caps, 1px `--ink` outline, 2px radius, 44px min height. Pressed state
  inverts (ink fill, paper text). Hover: 1px shift down, 120ms. No pills, no nested icon circles.
- **Links in prose**: ink, underlined 1px at 0.2em offset; hover turns the underline pen.
- **Tables**: no zebra, no boxes. Mono head row in `--ink-3` on `--paper-2`, `--grid-strong` rules between rows.
- **Readouts**: a mono label over a Newsreader number, left-aligned. Never a "stat card".
- **Empty/error states**: one sentence in Newsreader italic in `--ink-2`, plus the action if any.

## Motion

- Easing: `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)` for arrivals, `--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1)`
  for the paper advance. No bounce, no spring overshoot, no linear except the trace itself (data time is linear).
- Durations: 120ms hovers, 160ms ticks and fades, 240ms panels, 900ms the paper advance. That is all.
- Only `transform` and `opacity` animate in CSS. The canvas redraws per frame; nothing else does.
- No entry animations on scroll. Content is there when the page loads.
- Under `prefers-reduced-motion: reduce` every duration is 0 and the monitor is still (above).
- Animation pauses while the tab is hidden.

## Words

- The product words: **star**, **light curve**, **dip**, **signal**, **candidate**, **known**, **rejected**,
  **searched**. "Detection" is a code word; the UI says "dip" or "signal".
- **Candidate**, never "discovered", "new planet", "found a planet". A candidate is "a candidate, not a confirmed
  planet" wherever it is introduced.
- Data dates are always shown with the instrument: "observed 2 to 28 Aug 2026 by TESS".
- The monitor's mode is said plainly: "Live" or "Replay of the 26 Sep 2026 search".
- Votes: "Looks like a planet", "Probably not", "Not sure". Counts appear after voting.
- Rejections say why, in hunt's own sentence.
- Demo and stand-in data say so in the page header, once, in words ("These are stand-ins").
- No em dashes in UI copy. No exclamation marks.

## Accessibility

- Focus: 2px `--pen` outline, 2px offset, always visible.
- Every control has an accessible name; the monitor canvas has a live text twin (visually hidden) that announces
  each star and each dip ("Dip at 20 Jul, 2 950 ppm, known: TOI-7303.01") politely, at most once per 2 s.
- Text contrast meets WCAG AA on `--paper` and `--paper-2` in both themes.
- Tap targets are at least 44px on coarse pointers.
- Chart meaning is also in text: the dossier lists every mark it draws.
- `forced-colors: active`: the trace uses `CanvasText`, the pen `Highlight`, grain and grid are off.

## Code

- Bespoke CSS (CSS modules + `styles/tokens.css`). No Tailwind, shadcn/ui, Radix, Motion/Framer.
- The trace is hand-written 2D canvas code in `components/monitor/`, with its timing logic in plain TS that
  `node --test` can load.

## Where this file overrides skills

- **high-end-visual-design**: rejected its double-bezel cards, pill buttons with nested icon circles, glass
  floating nav, eyebrow pill badges, blur fade-up on scroll and "py-24 minimum" sections. They are the house style
  of generated sites, which the brief asks us not to be. Kept: its banned-font list, custom easing, transform/opacity
  only, no scroll listeners, `100dvh`, grain on a fixed layer.
- **design-taste-frontend**: Tailwind and Motion are out (bespoke CSS, canvas). Our uppercase mono labels are the
  label style and label data only.
- **emil-design-eng**: where it favours springs, we use the two curves above; the trace itself is linear in data
  time because data time is linear.
- **impeccable**: we keep hex tokens rather than OKLCH.

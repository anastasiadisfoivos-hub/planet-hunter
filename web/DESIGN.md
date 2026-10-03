# Planet Hunter: DESIGN.md

This file is authoritative for everything under `web/`. Where a skill, a library default or a habit disagrees
with it, this file wins, and the work says so.

Owned by the MONITOR-UI session. References and the reasoning behind them: `docs/monitorui/refs/README.md`.
Version 3 (27 Sep 2026): white sheet, heavy black type, icons that explain each screen.

## Direction: the chart recorder, on a white sheet

Planet Hunter is a planet finder and nothing else. Its home is a **monitor**: the star being searched streams its
real TESS light curve across the page as one continuous ink line, and when the search finds a dip, a red pen marks
it in the margin above the trace. The log is the recorder's drum (one row per star), candidates are dossiers, and
methods is the notebook.

It should look **built by hand, like an instrument panel**, not generated:

1. **One line is the hero.** No hero photograph, no 3D, no gradient. The trace is real data, labelled like an
   instrument trace.
2. **White sheet, black ink, one red pen.** Near-white paper, heavy black type, a red pen for what the search found,
   blue for what catalogues already knew, and each star's own temperature colour. Nothing else is coloured.
3. **Visible structure.** Hard edges, square corners, 2px black rules under headers, hairline rules between rows,
   ticks on the edges like a scale. Structure is drawn, not implied by shadows or cards.
4. **Icons explain, words label.** Every screen opens with a strip of 3 to 4 icons with two-word labels that says
   what you are looking at; a tap on an icon gives one sentence. Long explanations live in /methods.
5. **Deliberate, a little uneven.** Asymmetric columns, hand-tuned spacing, a mono scale that doesn't quite line up
   with the serif-less headings on purpose. Data is the imagery.
6. **Nothing loops for decoration.** Only the trace moves, and only while it is drawing a star.

Banned here: soft gradients, glows, blur, drop shadows, pill badges, rounded cards, uniform card grids, grain or
paper textures, generic hero copy ("Discover", "Explore the universe"), emoji. Not a game: no scores, points or
celebrations.

## Colour

Tokens in `styles/tokens.css` on `.site`. **Day is the default** whatever the operating system says; night is an
option in the top bar (a Day/Night switch, remembered in this browser), applied as `html[data-theme="night"]`.
All text pairs meet WCAG AA.

| token | day | night | use |
| --- | --- | --- | --- |
| `--paper` | `#FAFAF7` | `#0C0D12` | page ground, flat |
| `--paper-2` | `#EFEFEA` | `#16171F` | table heads, the sky map, the stand-in note |
| `--ink` | `#0B0B0A` (18.8:1) | `#F2F2EE` (17.3:1) | type, the trace, rules |
| `--ink-2` | `#3A3A36` (10.9:1) | `#BDBDB6` (10.3:1) | secondary text |
| `--ink-3` | `#5C5C56` (6.4:1; 5.8:1 on paper-2) | `#8F8F88` (6.0:1) | scale numbers and edge labels |
| `--pen` | `#C8260C` (5.4:1; 4.9:1 on paper-2) | `#FF6A4A` (6.9:1) | dips the search found, candidates, focus, the live dot |
| `--known` | `#1D55A0` (7.0:1) | `#86B2F0` (8.9:1) | objects already on a catalogue |
| `--grid` / `--grid-strong` | ink at 7% / 16% | paper-ink at 8% / 17% | chart divisions, row hairlines |

- **Star colour** (`components/monitor/starColour.ts`): each star in its blackbody colour from its TIC temperature
  (Mitchell Charity's table, chroma x1.6), orange-red near 2 500 K, near-white at the Sun, blue-white at 10 000 K,
  always inside an ink outline, always with the key. It never marks an outcome.
- Meaning is never colour alone: filled pen tick = candidate, blue tick with a bar = known, hollow ink tick =
  rejected, each with its word.

## Type

- **Archivo** (Omnibus-Type, SIL Open Font License 1.1), variable weight 100 to 900 and width 62 to 125, via
  `next/font/google` in `app/layout.tsx`. Headings **800** at width 112 (semi-expanded, like engraved panel
  lettering), names 700, body **500** at width 100, labels 600. Italic only for the pen's voice (a rejection's
  reason).
- **Martian Mono** (Evil Martians, SIL OFL 1.1) for every number and edge label: weight 500, width 87 for labels.

No other families. Banned: Inter, Geist, Space Grotesk, Newsreader, Roboto, Helvetica, Arial.

| token | size | use |
| --- | --- | --- |
| `--t-display` | 44 → 92px, line 0.92, tracking -0.035em, 800 | the star's name, page titles |
| `--t-h1` | 34 → 56px, 800 | section titles |
| `--t-h2` | 24 → 32px, 800 | sub-sections |
| `--t-body` | 17 → 19px, line 1.45, 500 | text |
| `--t-small` | 15px, 500 | captions |
| `--t-label` | 12px Martian Mono 500, uppercase, +0.06em | edge labels |
| `--t-num` | 15px Martian Mono 500, tabular | numbers |

## Space and grid

- 4px base (`--s-1` … `--s-9` = 4, 8, 12, 16, 24, 32, 48, 72, 112). Hand-tuned exceptions are allowed and commented.
- The page uses the whole screen: `--gutter: clamp(20px, 4vw, 80px)`, no centred column. Prose keeps 62ch.
- Every page head is **asymmetric**: the title takes the left 5 of 12 columns, the explainer strip and any facts
  the right 7, over a 2px ink rule.
- Corners are square everywhere (radius 0). Structure: a 2px `--ink` rule under page heads and table heads, 1px
  `--grid-strong` hairlines between rows, short tick marks at the ends of section rules.

## Icons (the glyph set)

Hand-drawn in `components/monitor/Glyphs.tsx`: one 1.5px stroke at 24px (scales with the icon), square line ends
for the frame, round ends for the trace, ink only; fills only for a star's temperature colour and the pen. No icon
library, no clip-art, no emoji.

- **Nav**: monitor (a trace with a pen), candidates (a planet crossing its star), log (drum rows), methods (a ruled
  notebook).
- **Explainers**: star, trace, pen, clock, sky, check, pixels, vote, catalogue, limits, step, honesty.
- **Star type**: disc sized by class (M → B), filled with the star's colour, dotted envelope for evolved stars.
- **Illustrations**: TESS (footer credit), empty trace ("no candidate yet").

### The explainer strip

At the top of every screen, one row of 3 or 4 items, each an icon + two words ("this star", "its brightness",
"dips found", "when observed"). Each item is a button; tapping or focusing it opens a one-sentence note right under
it (a toggletip: `aria-expanded`, closes on Escape, a second tap, or a tap elsewhere). No hover-only content.

## The monitor (the signature)

- **Paper**: a full-bleed transparent canvas over the page ground, ECG divisions (minor every day of data, major
  every 5) that move with the data under a fixed pen.
- **Trace**: one 1.5px `--ink` line; the pen head at 72% of the width; sector gaps are breaks with the sector
  printed, never bridged; in a gap the pen lifts.
- **Speed**: about 2.2 days of data per second, eased in and out; 60 fps on a 2D canvas.
- **Detections**: at the middle of each dip the pen writes a tick in the margin lane with a 1px rule down to the
  trace; the first dip of a signal carries its note (outcome word, period, depth), pinned at the page gutter once its
  dip scrolls away. Candidate and known dips are redrawn in their colour; rejected dips keep the ink line and a
  hollow tick. The notes under the monitor list each signal with hunt's reason.
- **Handover**: the finished trace holds 1.8 s, then slides off left in 900ms (`--ease-in-out`); the grid runs on.
  The header changes after the slide with a plain 160ms fade. A skip (Next star, →) advances in 240ms.
- **Mode**: top right, mono caps in a square box: `● LIVE` or `REPLAY` with "Replay of the 26 Sep 2026 search".
- **Tally**: stars searched, signals, candidates, all from `/monitor/stats`.
- **Reduced motion**: the whole curve drawn still, every tick shown, the star changes only on Next star. The
  animation pauses when the tab is hidden or the monitor is off screen.
- **Pointer / keyboard**: a cursor reading time and flux; Space pauses, → skips.

## Other pages

- **/candidates**: head (title, strip), the funnel as a ruled row of big numbers, then a table with the star's
  glyph, period, depth, size, checks, pixel check, vetting, your vote. The honest count comes first: when there is
  no new candidate the page says so with the empty-trace illustration, and stand-ins are marked as such.
- **/candidates/[id]**: dossier in two unequal columns (8 + 4): the dip (numbers, folded and whole curves), the
  checks, the pixel check, vetting, votes; the margin holds the star and the data dates. Votes appear after voting.
- **/log**: the Mollweide sky (Milky Way, ecliptic, TESS footprints, stars in their colours, outcome rings), then
  one row per star with its whole-curve trace, or "no curve stored".
- **/sensitivity**: the injection-recovery grid as ink densities with numbers.
- **/methods**: the notebook, numbered in the order the search runs (a real sequence). Text from the PLAN session.
- `/finder/*` redirects (308) to the new pages.

## Components

- **Top bar**: 60px, paper, a 2px ink rule below. "Planet Hunter" in Archivo 800 width 112; then Monitor, Candidates,
  Log, Methods, each an icon + one word, the current one underlined with a 3px pen rule; Day/Night switch at the
  right. Phone: icons with their word under them, in one row.
- **Buttons**: Martian Mono 12px caps, 1.5px ink border, square, 44px high; pressed inverts; hover shifts 1px down.
- **Tables**: mono caps head on `--paper-2` with a 2px ink rule above; 1px hairlines between rows; no zebra.
- **Empty / error**: one short sentence with an icon.

## Motion

- `--ease-out: cubic-bezier(0.22, 1, 0.36, 1)`, `--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1)`.
- 120ms hovers, 160ms ticks, fades and tooltips, 900ms the paper advance. Only transform and opacity animate.
- No entry animations on scroll. Under reduced motion every duration is 0. Animation pauses when the tab is hidden.

## Words

- Product words: **star**, **light curve**, **dip**, **signal**, **candidate**, **known**, **rejected**, **searched**.
- **Candidate**, never "discovered", "new planet" or "found a planet".
- Data dates always with the instrument: "observed 2 to 28 Aug 2026 by TESS". The mode said plainly.
- Labels are two words where they can be; sentences go into tooltips and /methods. Rejections keep hunt's sentence.
- Votes: "Looks like a planet", "Probably not", "Not sure", counts after voting.
- No em dashes, no exclamation marks.

## Accessibility

- Focus: 2px `--pen` outline, 2px offset. Every control named; icons that carry meaning have a text label beside
  them, decorative ones are hidden from assistive tech.
- The monitor's live text twin announces each star and each dip, politely, at most every 2 s.
- AA contrast in day and night; 44px targets on touch; chart meaning also in text; tooltips reachable by keyboard.

## Code

- Bespoke CSS modules and `styles/tokens.css`. No Tailwind, shadcn/ui, Radix, Motion/Framer, icon libraries.
- The trace and all charts are hand-written canvas or SVG.

## Where this file overrides skills

- **design-taste-frontend**: it bans hand-rolled SVG icons and asks for an icon library; here the icons are drawn
  by hand in one stroke on purpose (the owner asked for it; the set must match the trace). It asks for real photos
  on every page; the data is the image. It prefers Motion and Tailwind; bespoke CSS and canvas instead. Its eyebrow
  limits: our mono caps label data, never sections.
- **impeccable**: hex tokens rather than OKLCH; the methods page's step numbers are a real sequence.
- Earlier versions of this file chose warm paper, Newsreader and night glows; v3 drops all three.

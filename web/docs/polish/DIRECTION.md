# POLISH direction

Status: **proposal for review**. Nothing here is built yet. The evidence is in `refs/` (8 Awwwards references),
`extracted/` (measured tokens from Resend and Claude on Mars), `critique.md` (7 pages, two independent
assessments) and `mocks/` (home and a candidate report, before and after, 1440 and 390).

## The direction in five sentences

1. Planet Hunter becomes one instrument instead of three sites: one top bar, one page-header pattern and one
   1200px grid shared by home, lab, finder and the map.
2. Black is the canvas and hairlines are the structure. Pages sit on the same `#000` as the sky, sections are
   ruled rather than boxed, and a raised surface appears only for things that float.
3. Type does the hierarchy. Geist writes the sentences, and Geist Mono sets every number and label.
   The scale has eight steps, and each page gets one confident size instead of many middling ones.
4. Colour belongs to data and to real pictures. Chrome is three greys, and `#A3B8FF` appears only where
   something is selected or focused.
5. Every claim carries its basis in one caption grammar (value, unit, source, date), so honesty reads as design
   instead of as disclaimers.

## What stays

- Pure black `#000` sky (`--space`). The proposal extends it to the page canvas; it does not soften it.
- `--accent #A3B8FF`, reserved for selection, hover and focus. It becomes stricter: it leaves every chart.
- No game language: no points, scores, locks, unlocks, streaks or watches.
- "Candidate", never "discovered" or "new planet". Confidence always comes with its basis.
- Geist and Geist Mono (argued below). Dark only. Flat surfaces, no shadows, no glows in the UI.
- Bespoke CSS with custom properties. No Tailwind, no shadcn/ui, no Radix, no Motion or Framer library.
- The Motion section of DESIGN.md. It is untouched here because another session owns it.

## Conflicts, and what I recommend

| Question | Options on the table | Recommendation | Why |
|---|---|---|---|
| Page background | DESIGN.md `--bg #09090B`; design-taste skill bans `#000`; Resend, Claude on Mars and 21 HRS use `#000` | **`#000` for the page canvas**; `--raised #111214` for floating panels only | Home shows a hard seam at y=640 where the `#000` hero meets `#09090B` (critique, home). The map is `#000`. One black makes the four sections one place. |
| Hairlines | Solid `#1C1D21` / `#26282D` (today); translucent white (Resend: `rgba(214,235,253,.19)` and `.145`) | **Translucent**: three steps of `rgb(222 230 255 / .06, .10, .16)` | One token reads the same on `#000`, on `--raised` and over a picture. Solid greys look heavier on black than on the panel. The faint cool tint sits next to the accent's hue without being the accent. |
| Tag shape | DESIGN.md "pills only for tags"; refs use square tags (Auriga, Vast, Claude on Mars) | **4px radius, no pills anywhere** | Pills are the one soft shape left in a ruled system. Today there are 7 radius values (2, 3, 6, 8, 12, 999, 50%); this makes it 3 (plus 50% for dots). |
| Mono uppercase labels | DESIGN.md makes them the label style; impeccable bans "a tiny uppercase eyebrow above every section" | **Keep them, but only above a value, as a table header, or as a picture's source line.** Never as a section kicker; the one exception is the kind label in a detail page header ("PLANET CANDIDATE"). | Labels that name data are instrument grammar. Labels that decorate headings are the AI scaffold. |
| Label tracking | Today +0.06em; Auriga and Claude on Mars +0.01em; Singularität +0.12em | **+0.04em** | Geist Mono is already wide-set, and at +0.06em "CHANGE IN BRIGHTNESS" reads loose inside charts. +0.01em (the refs) is set for denser faces. |
| Display face | Claude on Mars uses a serif display; Resend adds ABC Favorit and Domaine | **Geist only** | A second family would split the voice between "story" and "instrument". Geist's 500 weight at -0.035em gives a confident display, and one family is also cheaper to load. |
| Button shape | Resend pills | **8px** | Buttons sit beside inputs and segmented controls; they should share the control radius. |
| Word "score" | Finder uses "Score" and "points"; DESIGN.md bans scores | **"Priority"** (a machine ranking, 0 to 1) | It is a ranking, and the report already says so. The word ban exists for a reason. |
| Status colour | Finder uses category green and yellow for pass and warn | **Neutral glyph plus word; `--supernova` only for fail or blocking** | Green means "solar system" on the map. Status must not borrow data colours. |
| The user's own model in charts | Today it is drawn in `--accent` | **Dashed `--ink` line**; measured or pipeline answer solid `--ink` | Keeps the accent's single meaning without adding a colour. |

## Rules

### Surfaces

| Token | Value | Use |
|---|---|---|
| `--space` | `#000000` | the sky; unchanged |
| `--bg` | `#000000` (was `#09090B`) | page canvas on every route |
| `--well` | `#070708` | rare: a chart or image area that needs to read as "inside" (pixel images, code) |
| `--raised` | `#111214` | floating only: the vote panel, popovers, sheets, the map's panels |
| `--bg-deep` | retired; use `--well` | |

A panel never sits on a panel. Sections never sit in panels.

### Hairlines

| Token | Value | Use |
|---|---|---|
| `--line-faint` | `rgb(222 230 255 / 0.06)` | row separators, top-bar bottom edge, gridlines in charts |
| `--line` | `rgb(222 230 255 / 0.10)` | section rules, card and panel borders, fact-grid rules (replaces `--hairline`) |
| `--line-strong` | `rgb(222 230 255 / 0.16)` | control borders, tags, a chart's zero line (replaces `--control-border`) |

Structure is made of hairlines plus space. A group of stats is a ruled grid (a rule above, a rule below, 1px
verticals between), never a box.

### Type

Geist for UI and prose; Geist Mono for numbers, coordinates, IDs and labels. Weights: 400 and 500 only
(600 is retired).

| Step | Size / line height | Tracking | Use |
|---|---|---|---|
| label | 11 / 16, mono, UPPERCASE | +0.04em | labels above values, table headers, picture sources, tags |
| meta | 12 / 16 | 0 | notes under values, captions, timestamps |
| small | 13 / 20 | 0 | secondary UI, nav on phones, supporting copy in dense areas |
| body | 14 / 20 | 0 | the UI default |
| read | 16 / 26 | 0 | ledes and reading text; max 640px |
| h3 | 20 / 26 | -0.015em | panel titles, door titles |
| h2 | 28 / 32 (24 / 28 on phones) | -0.025em | section headings |
| h1 | 40 / 44 (32 / 36 on phones) | -0.03em | page titles |
| display | clamp(36px, 5.2vw, 56px) / 1.04 | -0.035em | home hero only |

Retired: 15, 17, 24 (except as phone h2) and 32 (except as phone h1). Every paragraph gets `max-width: 640px`
(the star lab's 1,142px lines are the worst offender). Headings use `text-wrap: balance`, prose `text-wrap: pretty`.

### Numbers, units and labels

- **Number**: Geist Mono, `font-variant-numeric: tabular-nums`, `--ink`, tracking -0.01em (-0.02em at 20px and
  up). Sizes: 14 in tables, 20 in fact grids, 28 in readouts, 40 for the single hero number on a page.
- **Unit**: Geist (sans) at roughly 70% of the number's size, `--ink-secondary`, 0.2em gap. There is no gap for `%`,
  `°`, `′` and `″`. Units are words ("days", "hours", "× Earth") unless a symbol is standard (K, ly, σ, R⊕, Å).
- **Range and basis**: a meta line under the value in words: "likely 3.7 to 5.0", "95%, from the pixel check",
  "80%, machine guess". No ± in the UI.
- **Label**: the label step above the value, `--ink-muted`, with 6px from label to value.
- **One unit system per page**: planet sizes in Earth radii below 2 R♃, Jupiter radii above.
- **Times in running text are sans** ("2 days ago", "19 Sep, 18:17 UTC"). Mono is for tables and readouts.
  Today "2  d  ago" in mono reads with wide gaps.

### Spacing

4px base: **4, 8, 12, 16, 24, 32, 48, 64, 96**. 2 and 6 are allowed only as optical steps (label to value,
icon to text). 20 is retired.

- Inside a component: 8, 12 or 16.
- Between a heading and its content: 24.
- Between sections on app pages: 48, then a `--line` rule, then 48.
- Between sections on home: 64 to 96.

### Grid and widths

- Container: **1200px** content width, plus margins of 40px (≥1024), 24px (640 to 1023) and 16px (<640).
  The top bar uses the same container, so the wordmark and the content share a left edge.
- 12 columns, 24px gutter (16 on phones).
- Reading measure **640px**. Wide figures **880px**. Aside **320px**. Detail pages are main (832) plus aside
  (320) with a 48 gap.
- Breakpoints: 640 and 1024. Below 1024 the aside drops below the page header (never to the end of the page).

### Radius

`--r-tag 4px` (tags, picture corners, placeholders) · `--r-control 8px` (buttons, inputs, segmented, cards) ·
`--r-float 12px` (floating panels and sheets only) · `50%` (dots, colour discs). Nothing else.

### Buttons

| Tier | Look | Use |
|---|---|---|
| Primary | `--ink` fill, `#000` text, 13/500, 8px radius | one per view: Search on home, Analyze this star |
| Secondary | transparent, 1px `--line-strong`, `--ink` text | every other real action |
| Quiet | text only, `--ink-secondary`, → arrow when it navigates | "All 41 on the map →", "Data credits and sources" |

- Heights: 32 (default) or 40 (hero search, vote options), and 44 on coarse pointers for all of them.
- Padding: 12px horizontal (16 at 40px).
- Disabled: `--ink-disabled` text and a `--line-faint` border, and still focusable, with the reason in a tooltip
  or next to it. Never dashed.
- If an action is impossible for a known reason (a star not on the map), hide it and say why in one line.
- These replace today's 6 button styles and 4 heights.

### Tags

Mono label step, 20px high (24 in page headers), 4px radius, 1px `--line-strong`, `--ink-secondary` text.

- `DEMO DATA` is the one demo tag. Put it on the smallest thing that is demo, and add one caption sentence
  saying what is simulated.
- If the page is all demo, tag the page header only; never show "DEMO" and "REAL" at the same level.
- "REAL DATA" tags are removed: real is the default and does not need a badge.

### Cards

Cards are for two things only:

1. **A clickable item that carries a picture.** Even then it is a picture tile, not a box: the image (1:1 or
   4:3, 4px radius, flush) with text beneath on the canvas, and no border or fill.
2. **A floating panel.** `--raised`, 1px `--line`, 12px radius, 24px padding.

- Never nest.
- No card around a chart, a stat group, a list of links or a single sentence.
- Four identical boxes all saying "Not on the list" become one ruled row.

### Tables

- Header row: label step, `--ink-muted`, `--line` below.
- Rows: at least 44px, with `--line-faint` separators and no zebra striping. Hover tints the row 2%.
- First column is sans 14/500 `--ink`. Numbers are right-aligned, tabular, with units in sans.
- On phones keep 3 columns at most. Move IDs under names and drop explanatory columns (they live on the
  detail page).
- Star colour appears as a 12px disc from Teff, never as a coloured name.

### Empty, loading, error

- **Empty**: in place of the content, left-aligned. One sentence (14, `--ink-secondary`) saying what is empty and
  why, plus one secondary or quiet action. An optional 1px line drawing, at most 96px tall. No centred icon hero.
- **Loading**: reserve the final size. Placeholders are flat `rgb(222 230 255 / .04)` blocks with 4px radius, at
  real line heights and chart boxes. After 1s add a meta line saying what is loading ("Loading 2 sectors of
  TESS data"). Motion follows the Motion section.
- **Error**: inline where the data would be: what failed, what still works, and a secondary "Try again".
  - A missing optional file is **not** an error. Say "No spectrum is available for this star yet".
  - Never show developer copy ("service isn't connected", "arrive with the SPECTRA files", "for building the UI").
  - `--supernova` is only for errors that block the page.
- **Paused sources**: unchanged ("Rubin hasn't sent alerts since 14 Jul"), set as a meta line with a neutral dot.

### Page headers

One pattern on every page except home.

```
← Candidates                                     (quiet crumb, detail pages only)
PLANET CANDIDATE                                 (kind label, detail pages only)
TIC 219345170  [DEMO DATA]                        (h1, tag inline)
A dip every 3.81 days, found on 18 Sep 2026…      (read, max 640, one or two sentences)
[✓ 6 of 6 checks passed] [✓ On target] […]       (summary tags or a meta row, optional)
Candidates · What the search can find             (section tabs, index pages only)
──────────────────────────────────────────────── (32 below, then content)
```

Actions sit on the right of the h1 line, secondary tier at most. A primary action in a header only when it is the
page's one job ("Analyze this star").

### Top navigation (home, lab, finder and map)

- 56px tall, `#000`, 1px `--line-faint` bottom edge, sticky on app pages. On home it overlays the hero with no
  edge and scrolls away.
- Left: a glyph (ring plus dot) and "Planet Hunter" (14/500). It **always links to `/`**.
- Then **Sky map · Lab · Finder**: one name each, everywhere, including home's copy. 14px `--ink-secondary`.
  The current section is `--ink` with a 1px `--ink` rule on the bar's bottom edge. The current section is not
  "selection", so it does not use the accent.
- Right: **Find a star**, a 240px field with a `/` shortcut that opens the existing star search as a popover. On
  phones it collapses to a 32px icon button.
- Section navigation (Lab experiments, Finder's two views) moves out of the bar into the page header as tabs.
  This removes the 93px two-row bars at 390 and the hidden-scrollbar nav.
- **Map**: the same bar is the map's top row, above the sky. The map's own "Jump to · status · About" row
  continues below it. The map implementation belongs to MAPUI; this spec is the handoff.
- At <640: wordmark glyph only, links 13px, 44px tap height.

### Charts

- Charts sit on the canvas with no card. Gridlines are `--line-faint`, and the zero or reference line is
  `--line-strong`.
- Ticks: mono 11 `--ink-muted`. Axis titles: sans 12 `--ink-secondary`, sentence case, placed at the end of the
  axis. No uppercase inside plots.
- Series:
  - measured points `--ink-muted`;
  - the summary line (median, fit, the pipeline's answer) solid `--ink`, 1.5px;
  - **the user's own model or guess: dashed `--ink`**;
  - predicted events: `--ink` ticks;
  - categories use their data colours with their shapes.
- The accent appears in a chart only on the selected point or series.
- Legends sit under the chart, as meta text with the real mark drawn at size.
- The SVG viewBox matches the rendered width, so an 11px label renders at 11px. On phones use a narrow variant;
  never scale a desktop chart down.

### Imagery

- **Real pictures only**, as tiles: 1:1 thumbnails (4:3 when the source is wide), 4px radius, `object-fit:
  cover`, no border, no inner padding, no text over the picture.
- **Caption grammar under every picture**: line 1 is the source in the label step ("NASA SDO/AIA 131 Å · 2 min
  before peak", "DESI Legacy Surveys DR10 · archive"); line 2 is an optional sentence in meta.
  - Credits wrap; they are never cut to "…".
  - The archive caveat is stated once per section, and each archive picture carries "· archive" in its source line
    (it is not repeated as a paragraph on every card).
- **Drawings**: 1 to 1.5px line art in `--line-strong` plus data colours, for doors, empty states and the Finder's
  explanatory figures (Portal Space Systems). Drawings are labelled as drawings when they could be mistaken for
  data.
- **Star colour** is a disc from Teff (`lib/starColor.ts`).
- None of these: stock photos, 3D renders, gradient glows, or nebula art outside the sky's optional layer.

---

## Page by page (worst first)

Each change cites a critique finding (C) or a reference (R).

### /lab/star/[tic]

1. Remove the page-level DEMO tag when any card is real, and drop "REAL DATA" tags entirely (C: DEMO vs REAL, P1).
2. Replace developer copy and 404-driven states with neutral "not available for this star yet" lines
   (C: developer copy, P1).
3. Flatten to ruled sections: no section panels, no cards inside them, no chips inside cards. "Its planets' air"
   becomes a table row per planet (C: 3-deep nesting, P2).
4. Cap every paragraph at 640px (C: 1,142px lines).
5. Add a sticky in-page index of the six experiments under the header, as tabs on phones (C: six at full
   depth; R: Singularität's tick ruler, 21 HRS's chapter strip).
6. User guesses go dashed `--ink`; accent only on selection (C: accent as data colour).
7. At 390: narrow chart variants with 11px labels; the HR diagram labels get leader lines (C: collisions).

### /finder/[id]

1. Show vote counts only after voting (C: anchoring, P1). *Mock shows it.*
2. Vote panel: sticky rail on desktop; directly after the facts below 1024 (C: y≈5,700 on mobile, P1). *Mock.*
3. Remove the dashed "Open star lab" and "Fly to it"; keep the one-line reason (C: dead buttons). *Mock.*
4. "95%, from the pixel check"; Earth radii throughout; "Priority"; "Probably not a planet" (C: basis, units,
   word bans). *Mock.*
5. A summary tag row under the lede: checks, pixel verdict, known lists, priority (R: Portal's spec triplets;
   C: three signals for one fact). *Mock.*
6. Known lists become one ruled row; checks become a real table without the repeated "PASSED" (C). *Mock.*
7. Put the demo disclosure on the pixel images' own source line (C: sector 104 vs 81/82). *Mock.*

### /finder

1. "Priority" replaces "Score" everywhere, including the sort (C: word ban, P1).
2. The candidate list becomes a table at ≥640 with a legend row for the mini-bars. On phones it becomes rows with
   three values each, not 14 cards repeating four labels (C: legend-less bars, label noise).
3. Filters collapse to Sort plus one "Filter" menu. Pixel-check toggles become a single select (C: 7 controls).
4. The funnel stays; set it as a ruled readout like home's (R: Resend's three-grey ramp; C: working).

### / (home)

1. One black canvas: the hero and body share `#000`, and the seam goes (C: seam). *Mock.*
2. The week's counts become the hero's floor: a ruled readout with category glyphs, the time window, the DEMO tag
   and paused sources on one line (R: 21 HRS meta pairs; C: template rhythm). *Mock.*
3. Newest with pictures: four picture tiles, the source line under each, the archive caveat once
   (C: repeated caveat, truncated credits; R: Claude on Mars captions, Vast). *Mock.*
4. Three ways in: ruled columns with 1px line drawings, no nested black wells (C: weakest door art, nested
   surface; R: Portal's line art). *Mock.*
5. Famous stars become a table with Teff discs (C: four identical cards; R: Resend's tables). *Mock.*
6. "How we stay honest": the accent left rules go; a `--line-strong` top rule instead (C: accent as decoration).
   *Mock.*
7. The display h1 goes to 56px; the lede to 16/26 at 520px (R: extracted type scales). *Mock.*

### /lab

1. List the star labs: add "Start from a star" (search plus the four famous stars) below the experiments
   (C: star labs orphaned).
2. Experiments become tabs in the page header; "Finder" leaves the lab nav (C: section-in-section nav,
   hidden-scrollbar nav).
3. The DEMO explanation sits next to the first DEMO tag, not in the footer (C).

### /lab/hubble

1. The first state is labelled "Your line: 45 km/s/Mpc gives 21.7 billion years", so the wrong answer is
   clearly the user's line; the best fit is solid (C: wrong fact at display size).
2. One control: the on-plot handle gets a visible label, and the slider stays as the keyboard path with the same
   value (C: two controls).
3. Segmented control at 32/44px with a 4px inset (C: cramped padding).

### /finder/sensitivity

1. Candidate diamonds move beside the cell values, become focusable links with a TIC tooltip, and change glyph
   (the diamond belongs to "solar system" on the map) (C).
2. Heatmap text contrast of at least 4.5:1 at 11px (two cells fail) (C).
3. The "30" tick is not clipped at 390 (C).

---

## Top 10 changes (the order to build)

1. **One global top bar** across home, lab, finder and map. The wordmark goes to `/`, the names are Sky map · Lab ·
   Finder, "Find a star" sits on the right, and section navigation moves into the page header.
2. **One black canvas** (`--bg: #000`), with `--raised` reserved for floating panels. The home seam goes.
3. **Translucent hairline tokens** (`--line-faint`, `--line`, `--line-strong`) replace `--hairline` and
   `--control-border`.
4. **Ruled sections, no nested cards.** Star-lab panels, stat boxes and the known-lists cards become ruled
   grids and tables.
5. **The eight-step type scale** plus the number and unit grammar, prose capped at 640px, and relative times in
   sans.
6. **One demo grammar.** Fix the star lab's DEMO-vs-REAL contradiction and remove every line of developer copy.
7. **The accent leaves the charts.** The user's model is dashed ink, predicted ticks are ink, and status is a
   glyph plus a word with `--supernova` only for fail.
8. **The candidate report's honesty fixes**: votes after voting, the vote placed after the facts on mobile,
   "Priority", "Probably not a planet", Earth radii, "95%, from the pixel check".
9. **Home stops following the landing template**: a readout floor, picture tiles with captions, line-art doors,
   and a famous-stars table.
10. **One control system**: primary, secondary and quiet buttons at 32 and 40px (44 on touch), radius down to
    4/8/12, and tap targets of at least 44px on coarse pointers for nav, segmented controls and votes.

# planet-hunter web: DESIGN.md

This file is authoritative for everything under `web/`. If a skill, library default or habit conflicts with it,
this file wins.

**Direction:** a phenomena spotter: what is happening in the sky, each event at its real position, filterable,
with real pictures, plus every star clickable and analyzable. Think instrument or observatory software, **not a
game**: no watches, points or scores.
The UI is quiet and exact, with flat surfaces and hairlines. Data carries the colour; chrome stays neutral.

Home, events, sky, lab and finder are one instrument that **shows** the sky: every surface leads with a real
photograph or real instrument data, words shrink to a title, a name and one mono caption line, and every
explanation is one tap away. Black is the canvas, hairlines are the structure, and the page has generous air.
Events are a gallery of their own pictures (`/events`); the sky (`/sky`) is where they are. The reasoning is in
`docs/polish/DIRECTION.md`.

Tokens live in `app/tokens.css` as CSS custom properties. Components use tokens, never raw hex.
Shared primitives live in `components/ui/`. This file, `app/tokens.css`, `app/layout.tsx`, `app/globals.css`,
`components/ui/*` and `lib/api.ts` are **owned by the SPOTMAP session** (formerly SKYMAP); other sessions request changes through
the project owner.

## Colour

Dark only.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#000000` | page canvas on every route; the same black as the sky |
| `--well` | `#070708` | rare: an area that must read as "inside" (pixel images, code) |
| `--space` | `#000000` | the 3D sky's space. The sky's background is ESO's real all-sky photograph (eso0932a, "ESO/S. Brunier", CC BY 4.0) on this black; see The sky |
| `--raised` | `#111214` | floating things only: popovers, sheets, the vote panel, the map's panels. Never a section background. |
| `--line-faint` | `rgb(222 230 255 / 0.06)` | row separators, the top bar's bottom edge, chart gridlines |
| `--line` | `rgb(222 230 255 / 0.10)` | section rules, fact-grid rules, panel borders |
| `--line-strong` | `rgb(222 230 255 / 0.16)` | inputs, buttons, tags, a chart's zero line |
| `--ink` | `#F4F4F5` | primary text; the primary button fill |
| `--ink-secondary` | `#A1A6B0` | secondary text; units |
| `--ink-muted` | `#8B909A` | labels, helper text, captions |
| `--ink-disabled` | `#5D626B` | disabled text only. Never used for anything that must be read. |
| `--accent` | `#A3B8FF` | **the one accent**: selection, hover, focus, the selected event's error circle. Never a chart series, never a model line, never decoration. |
| `--rubin` | `#6FD6C6` | Rubin coverage (data colour) |
| `--supernova` | `#E8836A` | supernova detections (data colour); also used for blocking notices and failed checks |
| `--cat-transient` / `--cat-solar-system` / `--cat-sun` / `--cat-earth` / `--cat-high-energy` / `--cat-other` | `#E8836A` / `#8FD18A` / `#F2C14E` / `#7CC4F2` / `#D98BD8` / `#A1A6B0` | event categories (data colours). **Always paired with a shape**: ring, diamond, square, triangle, plus, dot (`lib/eventStyle.ts`); never colour alone. These shapes are reserved: no other UI reuses the diamond, ring, square, triangle or plus. |
| `--grid` | `#1F2127` | the faint RA/Dec grid on the sky |

Rules:

- The primary button is `--ink` fill with `#000` text. There is at most one primary button per view.
- No glows, gradient washes, shadows or emoji **in the UI**. The sky is the exception: stars and the close-up star
  glow through a bloom pass (see The sky). Translucent tints of a token (for example, a 12% `--accent` fill on
  a selected row) are allowed. A data legend may show a colour ramp; nothing else uses a gradient.
- Data colours (`--rubin`, `--supernova`, and the per-type colours added later) appear only on data: the map,
  charts, legends and tags.
- Status (passed, on target, not on a list) is a neutral glyph plus a word. Category colours are never
  status colours. Only a failed or blocking state uses `--supernova`.

## Type

- **Geist** for UI. **Geist Mono** for every number, coordinate and uppercase label.
  Both come from the `geist` package, wired in `app/layout.tsx`.
- Weights 400 and 500 only. Headings are 500.
- Scale (size / line height / tracking):

  | Step | Size | Tracking | Use |
  |---|---|---|---|
  | label | 11 / 16, mono, uppercase | +0.04em  | above values, table headers, picture sources, tags |
  | meta | 12 / 16 | 0 | notes under values, captions, timestamps |
  | small | 13 / 20 | 0 | secondary UI |
  | body | 14 / 20 | 0 | the UI default |
  | read | 16 / 26 | 0 | ledes and reading text |
  | h3 | 20 / 26 | -0.015em | panel titles |
  | line | 16 / 24 | 0 | the one line under a heading (max 560px) |
  | h2 | clamp(24px, 2.2vw, 32px) / 1.1 | -0.03em | section headings (≤ 3 words) |
  | h1 | clamp(32px, 3.6vw, 48px) / 1.05 | -0.035em | page titles |
  | display | clamp(40px, 5.6vw, 80px) / 1.0 | -0.04em | the hero statement on a photograph (≤ 12 words); home and lab only |

  15, 17 and the 24/32 desktop heading sizes.
- No paragraphs on landing surfaces (home, /events, /lab, /finder). Elsewhere every paragraph has `max-width: 560px`. Headings use `text-wrap: balance`, prose `text-wrap: pretty`.
- Uppercase appears only in mono labels. A mono label names data: it sits above a value, heads a table
  column, or is a picture's source line. It is never a kicker above a section heading. The one exception is the
  kind label in a detail page's header ("PLANET CANDIDATE").

### Numbers and units

- Numbers: Geist Mono, `tabular-nums`, `--ink`. 14 in tables, 20 in fact grids, 28 in readouts, 40 for the one
  hero number on a page.
- Units: Geist at about 70% of the number's size, `--ink-secondary`, 0.2em gap (none for `%`, `°`, `′`, `″`).
  Words ("days", "× Earth") unless a symbol is standard (K, ly, σ, R⊕, Å).
- Ranges and bases in words, in a meta line under the value: "likely 3.7 to 5.0", "95%, from the pixel check".
  No ± in the UI.
- One unit system per page: planet sizes in Earth radii below 2 Jupiter radii.
- Times in running text are sans ("2 days ago"). Mono is for tables and readouts.

## Shape and space

- 1px hairline borders. Radius: 4px for tags, picture corners and placeholders; 8px for controls
  and cards; 12px for floating panels and sheets only; 50% for dots and colour discs. pills.
  Flat surfaces, no shadows (and no inset box-shadows standing in for borders).
- The spacing scale is 4, 8, 12, 16, 24, 32, 48, 64, 96, 128, 160, from a 4px base. 2 and 6 only as optical
  steps (label to value, icon to text). 20.
- Section padding: 160 on landing surfaces (128 at 640 to 1023, 96 on phones); 96 on app pages (80, 64).
  Section head to content 40. Picture grids: 24 column gap (12 on phones), 40 row gap (28 on phones). Picture to name 12,
  name to caption line 2. Editorial split gap 96.
- Controls are 32px tall (`--control-h`), or 44px on coarse pointers. A large control (hero search,
  vote options) is 40px, also 44px on coarse pointers. The segmented control and nav links follow this too.

### Grid

- Container: 1312px content, with margins of 64px (≥1280), 40px (1024 to 1279), 32px (640 to 1023) and 20px (<640).
  The top bar uses the same container.
- Picture grids: 5 columns ≥1280, 4 ≥1024, 3 ≥640, 2 on phones. Reading measure 560px; side columns 360 to 400px.
- Breakpoints: 640 and 1024. Below 1024 an aside moves up under the page header, never to the end of the page.

### Surfaces and cards

- Sections are ruled, not boxed: 48px, a `--line` rule, 48px (64 to 96 on home).
- A group of values is a ruled grid (a rule above and below, 1px verticals), never a box.
- Cards are only for (1) a clickable item with a picture, drawn as a picture tile with text on the canvas and no
  box, and (2) floating panels (`--raised`, 1px `--line`, 12px radius, 24px padding). Never nested.

## Components

### Top bar

- 56px, `#000`, a `--line-faint` bottom edge, sticky on app pages. On home it overlays the hero with no edge.
- Left: glyph plus "Planet Hunter", always linking to `/`. Then **Events · Sky · Lab · Finder**. These are
  the only names for the sections, everywhere. 64px tall (56 on phones); transparent over a hero photograph. 14px `--ink-secondary`; the current section is `--ink` with a 1px `--ink` rule
  on the bar's bottom edge (not the accent).
- Right: "Find a star", a 240px field with a `/` shortcut that opens the star search. On phones it becomes an icon
  button.
- Section navigation (lab experiments, finder views) lives in the page header as tabs, not in the bar.
- On `/sky`, the same bar is the top row above the sky.

### Page header

A crumb (detail pages), then the kind label (detail pages), then the h1 with tags inline, then a one-to-two
sentence lede (read, 640px), then a summary tag row or meta row, then section tabs (index pages). 32px below.
Actions sit right of the h1, secondary tier. A primary action appears only when it is the page's one job.

### Buttons

- Primary: `--ink` fill, `#000` text, 13/500, 8px radius.
- Secondary: transparent, 1px `--line-strong`, `--ink` text.
- Quiet: text only, `--ink-secondary`, with an arrow when it navigates.
- Disabled: `--ink-disabled` text, a `--line-faint` border, focusable, reason given. Never dashed.
- An action that is impossible for a known reason is hidden, with the reason in one line.

### Tags

Mono label step, 20px high (24 in page headers), 4px radius, 1px `--line-strong`, `--ink-secondary`.

### Tables

- Header: label step, `--line` below.
- Rows: at least 44px, `--line-faint` separators, no zebra striping, 2% hover tint.
- First column: sans 14/500. Numbers are right-aligned and tabular.
- At most 3 columns on phones.

### Charts

- On the canvas, no card. Gridlines `--line-faint`, zero line `--line-strong`.
- Ticks: mono 11. Axis titles: sans 12, sentence case.
- Measured points `--ink-muted`. The summary, fit or pipeline answer is solid `--ink` at 1.5px. **The user's own
  model or guess is a dashed `--ink` line.** Predicted events are `--ink` ticks.
- The accent appears only on the selected point or series.
- The viewBox matches the rendered width. Phones get a narrow variant.

### States

- **Empty**: a sentence where the content would be, plus one action. Optional line drawing, at most 96px.
- **Loading**: flat `rgb(222 230 255 / .04)` placeholders at final size; after 1s, a meta line naming what is
  loading.
- **Error**: inline: what failed, what still works, "Try again". A missing optional file is "not available for
  this star yet", never an error and never developer copy.
- **Demo**: one `DEMO DATA` tag on the smallest demo thing, plus one caption sentence. "REAL DATA" tags are not used.

### Pictures

- **Only real pictures:** photographs and instrument images from NASA, SDO/Helioviewer, ESA/Webb, ESA/Hubble, ESO,
  NOIRLab and ESA/Gaia; hips2fits survey cutouts; our own renders of real data. Never generated images, artist's
  impressions shown as photographs, stock space art, tinting or text burned into a crop.
- Every picture lives in `public/images/` with an entry in `public/images/credits.json` (url, title, credit, licence,
  source, size, archive?, event?).
- **Hero:** one full-bleed photograph (100vh, at most 920px). Only the page title may sit on it, in its dark negative
  space.
- **Tiles:** 1:1 in grids (3:4 or 4:3 for lab pictures), `cover`, 4px radius, no border, no overlay. Astronomical
  objects are shown whole unless the viewport edge cuts a planet on purpose.
- **Caption line:** one mono line (label step) under every picture: source · date or time · flag (`archive`,
  `guess 82%`, `candidate`, `demo`), with an **i** at its end that opens the credit, licence, source link and one
  honesty sentence.
- **Crosshair on archive pictures:** every survey or archive picture of an event carries a thin crosshair at the
  event's position (1px `--ink`, four 6px arms with a 5px gap at the centre, at 80% opacity), in the gallery and on
  the event page, so the picture is about the event. The caption still says "archive".
- **Typographic tile:** for an event with no picture and no precise position. A 1:1 `--well` square with a `--line`
  border, its category shape, its name and "TYPE · DATE". Never a stand-in image.
- **Data as picture:** light curves and pixel maps render large, labels at 1:1, with a caption line.

### Drawers

Every explanation lives in a closed `<details>` drawer: a 56px row with a summary of ≤ 3 words, a mono state on
the right ("6 of 6 passed") and a + / − marker. Science pages (lab experiments, the candidate report) keep their
full explanations, collapsed; the picture or chart leads. On the candidate report the folded light curve is the
large lead image and the survey picture of the star's field is the small one.

## Motion

- UI: 120 to 200ms, `cubic-bezier(.2, 0, 0, 1)`, on opacity, transform and colour only. Motion is for feedback
  and state change only; no UI element loops. Under `prefers-reduced-motion`, every duration is 0.
- Panels, popovers and sheets may use up to 240ms to enter and 160ms to exit. Map markers may fade over up to 240ms.
- Camera: `camera-controls` gives damped orbit and dolly with inertia. Picking a planet host, "Jump to" and closing a
  close-up are **flights**: one eased (ease-in-out) timeline of 1.2 to 2 s that pulls back, turns toward the
  destination, then glides in. Any pointer or wheel input stops a flight where it is.
- Hover and selection rings on the sky fade in under 150ms.
- Two things loop: the focused star's surface (slow convection), and a gentle pulse on events observed in the last
  24 hours (a ring that grows and fades every 2.4 s). A running analysis step shows a spinner.
- Under `prefers-reduced-motion`: flights are instant cuts, no inertia, no drift, no pulse, no spinner, and the surface is a still image.
- The illustrated sky's nebula layer may drift very slightly (under 0.1°). This is off under reduced motion and on
  phones.
- Animation pauses while the tab is hidden.

## The sky

The sky becomes secondary: a full-screen page at `/sky` and a compact "where is it" on each
event. Its background is ESO's real all-sky photograph, eso0932a ("ESO/S. Brunier", CC BY 4.0), which is
equirectangular in galactic coordinates: it maps directly onto the celestial sphere rotated from galactic
to ICRS. Faint constellation lines (22 to 35%) and names (label style, 55%) come from d3-celestial (BSD-3-Clause),
so a position reads as "in Orion, near the Milky Way". Events are their category shapes. The compact sky is a
56° × 34° crop around the event. `/sky` wraps the panorama onto the 3D celestial sphere
with the camera inside (drag to look around, with inertia); the filter bar floats on top; the flat panorama is used
only for the compact crops. Map panels use `--raised` with `--line` borders, and the shared top bar is the sky's top
row. The panorama is served at 6000 × 3000 on desktop (ESO's largest JPEG; about 16.7 px per degree, so the default field
of view is 90°) and 3072 × 1536 on phones. Where the rules below say "pure black space" or "no haze", read
them as: nothing is added to the photograph; the page around it is `#000`.

- The sky is where the beauty lives. Panels stay flat and minimal.
- Reference: NASA's Eyes on Exoplanets. Pure black space (`--space`), jewel-like stars in their true colours, and
  fly-in close-ups of a star with a living surface.
- **Star colour is data.** Colour comes from effective temperature (TIC Teff for planet hosts; B−V converted to Teff
  for bright stars) through Mitchell Charity's blackbody table, with one documented saturation boost
  (`DISPLAY_SATURATION` in `lib/starColor.ts`, stated in "About this map"). Missing Teff: neutral white, no boost.
- Far stars are additive point sprites: a sharp core plus a gaussian halo, sized by apparent magnitude, drawn in
  device pixels. No twinkling. A bloom pass (luminance threshold, mipmap blur; half resolution on phones) makes only
  the brightest stars and the close-up star glow.
- Close-up: only the focused star swaps from sprite to sphere. Its radius is the catalogue radius on one scale for all
  stars, so relative sizes are true. The surface (granulation, spots, limb darkening) and corona are procedural, and
  the HUD always says "Surface is an illustration; colour, size and position are from real data."
- The illustrated layers (Milky Way, dust, Magellanic Clouds, nebulae) are procedural shaders placed at **real**
  positions and sizes from public catalogues (see `CREDITS.md`). They form one optional layer, "Milky Way & nebulae",
  **off by default**, with the note "Shapes are illustrations; positions are real." A drawn nebula is never labelled
  as a photo. Rubin coverage stays a subtle optional overlay.
- **Events pop.** Markers are 14 to 20 px at any field of view, with a 2.4 px stroke, a soft halo in their category
  colour and a thin black separation, drawn above the stars. "Dim stars" (on by default) draws stars at half
  brightness, so events are the brightest things on screen. A selected event dims the others and shows its error circle.
- **Every visible star is clickable**: planet hosts (3D, with the close-up) and bright catalogue stars (centred from
  Earth). Hover shows its name. The star panel says where each number comes from; estimated values (a bright
  star's temperature from B−V, its radius from brightness and temperature) are marked as estimates.
- If both star layers are off, a small hint says so, with a one-click "Show stars".
- Sun-frame events sit around the Sun's current position (computed client-side); the Sun itself is drawn in its
  real colour. Earth-frame events (fireballs, storms) are not on the sky: they get an Earth inset in the detail.
- **Black means black.** The background is `#000` at all times, including behind a close-up: the corona is gone
  by 1.5 stellar radii and the bloom threshold only catches star cores. No haze, fog or tint.

## Words

- Say **event**, never catch, trap or detection. There are no watches, forecasts, points or scores anywhere.
  The finder's machine ranking is **priority**, never score. No locks or unlocks.
- The star action is **Analyze this star**. A result is "Planet candidate", never "new planet", with its confidence.
- Never write "new planet" or "discovered". Confidence is always shown with its basis: "72%, machine guess".
- A vote is "Looks like a planet", "Probably not a planet" or "Not sure". Never "fake". Vote counts appear
  after the viewer votes.
- The sections are **Sky map**, **Lab** and **Finder**, in the UI and in prose.
- Pictures keep their caption and credit visible. A sky-context photo is an archive image taken years before the
  event: say so ("The event itself is not in it"). A `forecast_map` is labelled as a forecast, never a photo.
  Say it once per section; each archive picture's source line ends in "· archive".
- Paused sources are stated plainly: "Rubin hasn't sent alerts since 14 Jul."
- Dates: "14 Jul", "19 Sep 2026, 18:17 UTC". Times are UTC. Relative times come from `observed_at` only. When a
  source publishes no report time (`raw.reported_at_known === false`), say "Report time not published".
- Mock data shows a visible `DEMO DATA` tag.
- No developer copy in the UI (file names, services, "for building the UI").
- Word budgets: home hero ≤ 12 words; a landing section is a heading of ≤ 3 words plus at most one line of
  ≤ 8 words; no paragraphs on landing surfaces; a caption line is ≤ 8 mono tokens; a tile is a name of ≤ 4 words
  plus its caption line.
- Honesty stays one tap away at most: "archive" and "guess" in the caption line, "candidate" under the
  title, "demo" as a tag.
- No em dashes in UI copy.

## Layout: sky screen (/sky)

```
┌─────────────────────────────────────────────────────────────┐
│ top bar 64px: Planet Hunter · Events · Sky · Lab · Finder   │
├──────────────────────────────────────────────┬──────────────┤
│ filter bar (time, categories, More)          │ Detail       │
│                                              │ 360px, only  │
│   3D sky: ESO's photograph on the sphere,    │ when an      │
│   faint constellations, event shapes         │ event or a   │
│                                              │ star is open │
│ Layers                Jump to · paused · Pictures           │
├──────────────────────────────────────────────┴──────────────┤
│ status bar 36px: pointer RA/Dec, FOV, events shown, DEMO    │
└─────────────────────────────────────────────────────────────┘
```

With nothing selected the sky takes the full width; the list of events is the `/events` gallery (same filter bar and
URL params: `time`, `from`, `to`, `types`, `src`, `conf`, `pics`, `rubin`). `/map` redirects to `/sky` with its query;
`/sky?event=<id>` flies to an event and opens it; `/sky?host=<tic>` and `/sky?bright=<index>` fly to a star.
Below 900px the sky is full screen and an open event or star is a sheet.

## Accessibility

- Focus is always visible: a 2px `--accent` outline with a 2px offset.
- Every control has an accessible name.
- Text contrast meets WCAG AA on `--bg` and `--raised`.
- `--ink-disabled` is only for disabled text.
- Tap targets are at least 44px on coarse pointers, including nav links, segmented options and vote
  buttons.
- Meaning shown by a chart mark or mini-bar is also shown in visible text or a legend, not only in
  `aria-label`.

## Where this file overrides the design-taste-frontend skill

- The skill's default is Tailwind v4; we use bespoke CSS with custom properties.
- The skill's default is the Motion library; we use CSS transitions.
- The skill says light and dark modes are mandatory; this project is dark only.
- The skill targets landing pages (its §13); this is an app surface, so only its anti-slop, a11y and type rules apply.
- The skill bans pure `#000`; the sky is pure black by the project owner's decision ("black means black").
  The page canvas is pure black too, so pages and the sky are one surface; floating panels use
  `--raised`.
- The skill limits uppercase eyebrows; mono uppercase labels are this system's label style (Type, above).
  They label data only, never sections.

## Where this file overrides the impeccable skill

- Impeccable bans "a tiny uppercase eyebrow above every section". We agree: our mono labels name data, and at most
  one kind label appears per page header.
- Impeccable asks for OKLCH and a seeded palette on new projects; this project keeps its committed hex tokens.

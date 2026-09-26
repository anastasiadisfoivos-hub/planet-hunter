# /impeccable audit: sky map page

Scope: `app/map`, `components/map` (including `scene/`). This ran after the filter redesign and the
motion pass. DESIGN.md is authoritative: findings it disagrees with were rejected, as listed below.

Method: impeccable's static detector (`detect.mjs`) over the map files, then runtime checks in
Chromium at 1440×900 and at 390×844 (touch, coarse pointer). The runtime checks measured text
contrast against the real background and inherited opacity, touch-target size, horizontal overflow,
accessible names, heading order, computed transition durations with and without reduced motion, and
keyboard/Esc/focus return.

## Scores

| # | Dimension | Before | After | Key finding |
|---|---|---|---|---|
| 1 | Accessibility | 3 | 4 | the "0" on a dimmed chip was 3.13:1 |
| 2 | Performance | 3 | 4 | FLIP read layout on every render; the marker buffer re-uploaded every frame |
| 3 | Responsive | 3 | 4 | time segments (38 px), Reset (28 px) and the Feed tab (40 px) were under 44 px on touch |
| 4 | Theming | 4 | 4 | tokens throughout; the one literal is `#000` inside a `mask-image` |
| 5 | Anti-patterns | 4 | 4 | detector: no hits |
| | **Total** | **17/20** | **20/20** | |

**Anti-pattern verdict:** pass. No gradient text, glass, side stripes, card grids or hero metrics. The
sky is the only place with glow (the bloom pass), as DESIGN.md allows.

## Fixed (DESIGN.md agrees)

| Sev | Issue | Where | Fix |
|---|---|---|---|
| P1 | Dimmed zero-count chip: "0" at 3.13:1 (11px), under WCAG AA | `.chip[data-empty]` | Dim the glyph and border only; label and count stay `--ink-muted` (about 6:1). DESIGN.md: "Text contrast meets WCAG AA". |
| P1 | Touch targets under 44 px on coarse pointers: time segments 38 px tall and 40 px wide, Reset 28 px, Feed tab 40 px | map.module.css | Under `(pointer: coarse)` the segments, Reset and the Feed tab are ≥ 44 px. DESIGN.md: "Controls are 32px tall, or 44px on coarse pointers." |
| P1 | Phone: the Layers button painted over an open More sheet (same z-level; the sheet lives inside the bar's stacking context) | `.filterBar`, `.layersDock` | Whichever holds an open panel is raised to `--z-sheet`. Found in the audit screenshots. |
| P2 | Feed FLIP read `offsetTop` of every row on every render, including hover re-renders | Feed.tsx | Runs only when the row order changes. |
| P2 | Layers popover cut off the Scale control at 900 px tall | `.overlay[data-placement="above"]` | Max height follows the viewport. |
| P3 | The marker alpha buffer was uploaded every frame after the fade had settled (the loop keeps running for the 24 h pulse) | Scene.tsx `EventMarkers` | The buffer is left alone once every marker has arrived. |

## Rejected (DESIGN.md or the brief wins)

| Suggestion | Why it was rejected |
|---|---|
| 44 px touch targets everywhere | DESIGN.md sets 32 px controls for fine pointers and 44 px for coarse ones. Desktop keeps 32 px (26 px inside the segmented control, matching the shared `Segmented`). |
| Drop the small uppercase labels above each group ("EVENT TYPES", "SOURCES", "STARS") as an eyebrow tell | DESIGN.md, Type: mono uppercase 11px labels are this system's label style. |
| Reduced motion should keep gentle opacity fades rather than go to zero | DESIGN.md: "Under prefers-reduced-motion, every duration is 0." The brief says the same ("all instant"). |
| Exponential ease-out (quart/expo) or a motion library for richer effects | DESIGN.md fixes the curve at `cubic-bezier(.2, 0, 0, 1)`. The project uses CSS transitions and no motion library. |
| No choreographed entrances on load (the feed stagger) | The brief asks for a short feed stagger. It is capped at 150 ms of delay and never blocks input. |
| Blur, backdrop-filter or shadow as motion and surface materials | DESIGN.md: flat surfaces, no shadows or glows in the UI. |
| Add a PRODUCT.md (`/impeccable init`) | Outside this session's fence. DESIGN.md already carries the product direction. |

## Positive findings

- Every control has an accessible name. Chips expose on / off / mixed through `aria-pressed`, and More
  says how many settings are active.
- Tab order follows the screen: filter bar, Layers, then Jump to, About the data, Lab and Finder.
  Closed popovers are `inert`, so they are skipped.
- No horizontal page overflow at 390 px. The chip row scrolls inside its own box and fades at the edge.
- With reduced motion, every transition in the map measures 0s and no animations run.

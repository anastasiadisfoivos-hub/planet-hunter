# planet-hunter web: DESIGN.md

This file is authoritative for everything under `web/`. If a skill, library default or habit conflicts with it,
this file wins.

**Direction:** a pristine, modern exploration tool. Think instrument or observatory software, **not a game**.
The UI is quiet and exact, with flat surfaces and hairlines. Data carries the colour; chrome stays neutral.

Tokens live in `app/tokens.css` as CSS custom properties. Components use tokens, never raw hex.
Shared primitives live in `components/ui/`. This file, `app/tokens.css`, `app/layout.tsx`, `app/globals.css`,
`components/ui/*` and `lib/api.ts` are **owned by the SKYMAP session**; other sessions request changes through
the project owner.

## Colour

Dark only.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#09090B` | app background |
| `--bg-deep` | `#050506` | the map and charts |
| `--raised` | `#111214` | panels, inspectors, popovers |
| `--hairline` | `#1C1D21` | dividers and panel borders |
| `--control-border` | `#26282D` | inputs, segmented controls, ghost buttons |
| `--ink` | `#F4F4F5` | primary text; the primary button fill |
| `--ink-secondary` | `#A1A6B0` | secondary text |
| `--ink-muted` | `#8B909A` | labels, helper text |
| `--ink-faint` | `#737883` | disabled text, tertiary meta (large or non-essential text only) |
| `--accent` | `#A3B8FF` | **the one accent**: watches, planet hosts, selection, focus |
| `--rubin` | `#6FD6C6` | Rubin coverage (data colour) |
| `--supernova` | `#E8836A` | supernova detections (data colour); also used for blocking notices |

Rules:

- The primary button is `--ink` fill with `--bg` text. There is at most one primary button per view.
- No glows, gradient washes, shadows or emoji. Translucent tints of a token (for example, a 12% `--accent` fill on
  a selected row) are allowed.
- Data colours (`--rubin`, `--supernova`, and the per-type colours added later) appear only on data: the map,
  charts, legends and tags.

## Type

- **Geist** for UI. **Geist Mono** for every number, coordinate and uppercase label.
  Both come from the `geist` package, wired in `app/layout.tsx`.
- Headings are weight 500 with `letter-spacing: -0.035em`. Body text is 14 to 17px, and the default is 14.
- Scale: 11 (mono caps labels), 12, 13, 14, 15, 17, 20, 24, 32.
- Uppercase appears only in mono labels (`--font-mono`, 11px, `letter-spacing: 0.06em`).

## Shape and space

- 1px hairline borders. Radius 8px for controls and 12px for panels. Pills only for tags. Flat surfaces, no shadows.
- The spacing scale is 4, 8, 12, 16, 20, 24, 32, 48, from a 4px base.
- Controls are 32px tall (`--control-h`), or 44px on coarse pointers.

## Motion

- 120 to 200ms, `cubic-bezier(.2, 0, 0, 1)`, on opacity, transform and colour only.
- Motion is for feedback and state change only; nothing loops. Under `prefers-reduced-motion`, every duration is 0.
- No camera animations in this pass.

## Words

- Say **watch**, not trap. Say **detection**, not catch. Say **Analyze**, not hunt. The results page is **Discoveries**.
- API paths keep their contract names (`/traps`, `/hunt`). Only the UI copy changes.
- Never write "new planet" or "discovered". A type is a best guess and always carries its confidence:
  "Likely supernova, 72%".
- Explore mode has no points, scores, payouts or leaderboards anywhere.
- Mock data shows a visible `DEMO DATA` tag.
- No em dashes in UI copy.

## Layout: map screen

```
┌──────────┬──────────────────────────────────┬──────────────┐
│ Layers   │                                  │ New watch    │
│ 248px    │   3D sky (bg-deep, faint RA/Dec  │ inspector    │
│          │   grid)                          │ 360px        │
├──────────┴──────────────────────────────────┴──────────────┤
│ status bar 36px: coordinates under pointer, FOV, data dates │
└─────────────────────────────────────────────────────────────┘
```

Below 900px, the side panels become bottom sheets over the full-width sky, and the status bar stays.

## Accessibility

- Focus is always visible: a 2px `--accent` outline with a 2px offset.
- Every control has an accessible name.
- Text contrast meets WCAG AA on `--bg` and `--raised`.
- `--ink-faint` is never used for essential small text.

## Where this file overrides the design-taste-frontend skill

- The skill's default is Tailwind v4; we use bespoke CSS with custom properties.
- The skill's default is the Motion library; we use CSS transitions.
- The skill says light and dark modes are mandatory; this project is dark only.
- The skill targets landing pages (its §13); this is an app surface, so only its anti-slop, a11y and type rules apply.

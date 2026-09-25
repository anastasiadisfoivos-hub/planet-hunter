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
| `--bg-deep` | `#050506` | charts |
| `--space` | `#000000` | the 3D sky: pure black space |
| `--raised` | `#111214` | panels, inspectors, popovers |
| `--hairline` | `#1C1D21` | dividers and panel borders |
| `--control-border` | `#26282D` | inputs, segmented controls, ghost buttons |
| `--ink` | `#F4F4F5` | primary text; the primary button fill |
| `--ink-secondary` | `#A1A6B0` | secondary text |
| `--ink-muted` | `#8B909A` | labels, helper text |
| `--ink-faint` | `#737883` | disabled text, tertiary meta (large or non-essential text only) |
| `--accent` | `#A3B8FF` | **the one accent**: watches, selection, focus, and the hover/selection ring on planet hosts |
| `--rubin` | `#6FD6C6` | Rubin coverage (data colour) |
| `--supernova` | `#E8836A` | supernova detections (data colour); also used for blocking notices |
| `--ground-ecliptic` / `--ground-bulge` / `--ground-high` | `#D9BE7C` / `#D98BA6` / `#B7A5F0` | map "hunting grounds" layer only (data colours) |
| `--grid` | `#1F2127` | the faint RA/Dec grid on the sky |

Rules:

- The primary button is `--ink` fill with `--bg` text. There is at most one primary button per view.
- No glows, gradient washes, shadows or emoji **in the UI**. The sky is the exception: stars and the close-up star
  glow through a bloom pass (see The sky). Translucent tints of a token (for example, a 12% `--accent` fill on
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

- UI: 120 to 200ms, `cubic-bezier(.2, 0, 0, 1)`, on opacity, transform and colour only. Motion is for feedback
  and state change only; no UI element loops. Under `prefers-reduced-motion`, every duration is 0.
- Camera: `camera-controls` gives damped orbit and dolly with inertia. Picking a planet host, "Jump to" and closing a
  close-up are **flights**: one eased (ease-in-out) timeline of 1.2 to 2 s that pulls back, turns toward the
  destination, then glides in. Any pointer or wheel input stops a flight where it is.
- Hover and selection rings on the sky fade in under 150ms.
- The focused star's surface evolves slowly (convection). That is the only thing in the product that loops.
- Under `prefers-reduced-motion`: flights are instant cuts, no inertia, no drift, and the surface is a still image.
- The illustrated sky's nebula layer may drift very slightly (under 0.1°). This is off under reduced motion and on
  phones.
- Animation pauses while the tab is hidden.

## The sky

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
- Data (catalogue stars, planet hosts, Rubin coverage, watches) always draws on top and must stay
  readable over the brightest part of the band.

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

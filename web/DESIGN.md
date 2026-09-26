# planet-hunter web: DESIGN.md

This file is authoritative for everything under `web/`. If a skill, library default or habit conflicts with it,
this file wins.

**Direction:** a phenomena spotter: what is happening in the sky, each event at its real position, filterable,
with real pictures, plus every star clickable and analyzable. Think instrument or observatory software, **not a
game**: no watches, points or scores.
The UI is quiet and exact, with flat surfaces and hairlines. Data carries the colour; chrome stays neutral.

Tokens live in `app/tokens.css` as CSS custom properties. Components use tokens, never raw hex.
Shared primitives live in `components/ui/`. This file, `app/tokens.css`, `app/layout.tsx`, `app/globals.css`,
`components/ui/*` and `lib/api.ts` are **owned by the SPOTMAP session** (formerly SKYMAP); other sessions request changes through
the project owner.

## Colour

Dark only.

| Token | Value | Use |
|---|---|---|
| `--bg` | `#09090B` | app background |
| `--bg-deep` | `#050506` | charts |
| `--space` | `#000000` | the 3D sky: pure black space |
| `--raised` | `#111214` | panels, sheets, popovers |
| `--hairline` | `#1C1D21` | dividers and panel borders |
| `--control-border` | `#26282D` | inputs, segmented controls, ghost buttons |
| `--ink` | `#F4F4F5` | primary text; the primary button fill |
| `--ink-secondary` | `#A1A6B0` | secondary text |
| `--ink-muted` | `#8B909A` | labels, helper text |
| `--ink-faint` | `#737883` | disabled text, tertiary meta (large or non-essential text only) |
| `--accent` | `#A3B8FF` | **the one accent**: selection, hover, focus, the selected event's error circle |
| `--rubin` | `#6FD6C6` | Rubin coverage (data colour) |
| `--supernova` | `#E8836A` | supernova detections (data colour); also used for blocking notices |
| `--cat-transient` / `--cat-solar-system` / `--cat-sun` / `--cat-earth` / `--cat-high-energy` / `--cat-other` | `#E8836A` / `#8FD18A` / `#F2C14E` / `#7CC4F2` / `#D98BD8` / `#A1A6B0` | event categories (data colours). **Always paired with a shape**: ring, diamond, square, triangle, plus, dot (`lib/eventStyle.ts`); never colour alone |
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
- The star action is **Analyze this star**. A result is "Planet candidate", never "new planet", with its confidence.
- Never write "new planet" or "discovered". Confidence is always shown with its basis: "72%, machine guess".
- Pictures keep their caption and credit visible. A sky-context photo is an archive image taken years before the
  event: say so ("The event itself is not in it"). A `forecast_map` is labelled as a forecast, never a photo.
- Paused sources are stated plainly: "Rubin hasn't sent alerts since 14 Jul."
- Dates: "14 Jul", "19 Sep 2026, 18:17 UTC". Times are UTC. Relative times come from `observed_at` only. When a
  source publishes no report time (`raw.reported_at_known === false`), say "Report time not published".
- Mock data shows a visible `DEMO DATA` tag.
- No em dashes in UI copy.

## Layout: map screen

```
┌──────────┬──────────────────────────────────┬──────────────┐
│ Filters  │ Jump to · status banner · About  │ Feed         │
│ + map    │                                  │ (or Detail)  │
│ layers   │   3D sky (--space, faint grid)   │ 360px        │
│ 248px    │                                  │              │
├──────────┴──────────────────────────────────┴──────────────┤
│ status bar 36px: pointer RA/Dec, FOV, events shown, DEMO    │
└─────────────────────────────────────────────────────────────┘
```

Below 900px the sky is full screen; Filters and Feed are bottom sheets; an open event is a full sheet, and
"Show on map" closes it so the flight is visible. The status banner collapses into its "About the data" button.

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
- The skill bans pure `#000`; the sky is pure black by the project owner's decision ("black means black").
  Panels stay on the off-black tokens.
- The skill limits uppercase eyebrows; mono uppercase labels are this system's label style (Type, above).

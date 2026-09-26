# Extracted tokens: the two strongest references

Tool: `extract-design-system` (dembrandt, Chromium), run 26 Sep 2026 on one page each. Raw output sits in
`resend/` and `claude-on-mars/` (`raw.json` is the full dump, `normalized.json` and `starter-tokens.*` are the
tool's own summary). The tool's normalized summary dropped most colours and radii, so the tables below are
read from `raw.json` plus a computed-style sample of the same pages (`../refs/measurements.json`).

These are **reference measurements, not tokens to import**. Nothing here is wired into the app.
One page is not a whole design system; treat each number as "what this page does", not "what the brand does".

Why these two: Resend is the best product-grade dark UI in the set (tool chrome, code, tables, hairlines).
Claude on Mars is the best science story on pure black with real imagery and mono captions. Between them they
cover the two halves of Planet Hunter: the instrument (finder, lab, map chrome) and the story (home, star lab).

## Resend (resend.com)

| Primitive | Measured | Note |
|---|---|---|
| Page background | `#000000` | pure black page, not off-black |
| Text ramp | `#EBECED` primary (512 uses), `#A1A4A5` secondary (690 uses), `#464A4D` tertiary (168) | only three greys carry the whole page |
| Hairline | `1px solid rgba(214,235,253,0.19)` (63×); list rows `rgba(217,237,254,0.145)` | hairlines are **translucent white with a cold tint**, not a solid grey; they read the same on black and on a raised card |
| Faint rule | `rgba(211,237,248,0.114)` bottom rule | third, fainter step for dividers inside a card |
| Ring instead of shadow | `0 0 0 1px rgba(24,25,28,0.88)` (60×) | "shadows" are really 1px rings; no drop shadow anywhere in the dark UI |
| Display type | serif `domaine` 96 / 76.8px, lh 1.0, tracking -0.01em; `ABC Favorit` 56px, lh 1.2, tracking **-0.05em** (-2.8px) | one expressive display face, used only above the fold and in section titles |
| UI type | Inter 14px/20 (most common), 14/22.4 body, 16/24 lead, 18/27 hero lede, 12/16 meta | 14 is the workhorse; 12 is the floor |
| Mono | Commit Mono 12/16 (216×, code), 14/20, 16/24 | mono for code and for status values ("HTTP 200"), never for prose |
| Uppercase | Inter 12px 500 UC, no extra tracking | rare: a handful of tags |
| Weights | 400 body, 500 nav/labels, 600 buttons | three weights |
| Spacing | 2, 4, 6, 8, 12, 16, 24 (97×), 32, 48, 64, 96 (23×), 144 | 24 is the in-component gap; 96 is the section gap |
| Radius | 4 (19), 6 (58), 8 (30), 16 (62), 24 (10), pill (198) | pills for buttons and tags, 16 for cards, 6 to 8 for inner controls |
| Container | max-width 1280px (12×), 1024 for text-plus-media, 480 to 512 for ledes | |
| Header | 58px, transparent, no border at rest | |
| Buttons | primary: white fill, black text, 14px 600, pill; secondary: transparent, `rgba(255,255,255,0.05)` 2px ring, 16px radius | |
| Breakpoints | 480, 600 (plus Tailwind defaults) | |

## Claude on Mars (anthropic.com/features/claude-on-mars)

| Primitive | Measured | Note |
|---|---|---|
| Story background | `#000000` behind the planet and the story sections; page chrome `#141413` / `#FAF9F5` | the planet sits on true black |
| Text ramp | `#FAF9F5` warm white, `#B0AEA5` secondary (178), `#87867F` meta and hairline (138) | the hairline and the meta text are the **same colour**, which keeps the page quiet |
| Hairline | `1px solid #87867F` (25×, on cards and buttons); rows `1px 0` | solid, mid-grey, used sparingly |
| Display | serif 120px, weight 300, lh 0.85, UC tracking +2px; 86px UC; 44px/1.2 weight 300 section heads | light weight at huge size |
| Body | serif 19px / 1.55 (29.45px), measure 640px | long-form reading column |
| UI sans | 15px/1.4 nav, 13px/1.54 captions, 12px/1.4 small | |
| Mono captions | **13px, uppercase, +0.01em (0.13px), lh 1.2**, e.g. `DEC. 8, 2025 (SOL 1707)`, `SUPERCAM` | every image and instrument gets a mono caption with date and source |
| Sans caps label | 13px 700 UC +0.2px, e.g. `MARS PERSEVERANCE ROVER` | used as a kicker above a section |
| Spacing | 8, 12, 16 (30×), 24, 28.5 (21×, the body leading), 32, 48, 64, 80, 96 | |
| Radius | 2 to 4px on cards and camera frames; 50% dots | nearly square |
| Container | 1400px outer (29×), **640px text column** (22×), 800 / 872 for figures | text narrower than figures; figures break out of the column |
| Header | 68px, `#000`, no border | |

## What we take from each (and what we don't)

Take from Resend: translucent hairlines (one token that works on `--space`, `--bg` and `--raised`); a three-step
grey ramp; 14px as the UI workhorse with 12px as the floor; rings instead of shadows; 24px in-component and 96px
section rhythm; a 1280 container.

Take from Claude on Mars: mono uppercase captions with date and source under every picture; a 640px reading
column with figures breaking out to 872; true black behind the one hero image; meta text and hairline sharing a
colour.

Do not take: Resend's pill buttons (we keep 8px controls, see DIRECTION.md), its gradient-text accents
("this weekend" in a purple gradient), and its Tailwind/Radix stack. Claude on Mars's serif display face (Geist
stays; a second family would split the voice), and its light `#FAF9F5` page chrome (we are dark only).

# POLISH direction, v2: image-led

Status: **proposal for review**. Nothing in the app is rebuilt. v1 (`DIRECTION-v1.md`) is superseded wherever
this file differs, and kept for its rules on tokens, controls and wording.

Evidence:
- `refs-v2/`: 8 image-led Awwwards references.
- `mocks-v2/`: 7 static pages at 1440 and 390, built from the app's data by `mocks-v2/build.py`.
- `web/public/images/` with `credits.json`: 73 real, credited pictures.

## The direction in five sentences

1. Planet Hunter shows the sky instead of describing it: every surface leads with a real photograph or real
   instrument data, and words shrink to a title, a name and one mono caption line.
2. Events become a gallery of their own pictures, newest first: the SDO frame, the survey image of the host
   galaxy, the Rubin stamp. The sky becomes the "where is it", drawn on ESO's real Milky Way photograph with
   faint constellations.
3. Every explanation is still there, one tap away: behind an **i** on each picture, or in a collapsed drawer.
   "Archive", "guess" and "candidate" stay visible in the caption line.
4. The page is black and generous: sections open with 160px of air, pictures sit on a strict grid with 24px
   gutters, and nothing decorates what the pictures already say.
5. The v1 system underneath stays:
   - pure black, three greys, hairlines;
   - Geist and Geist Mono;
   - `#A3B8FF` for selection only;
   - one top bar;
   - "Priority", not "Score";
   - vote counts after you vote;
   - no game language.

## What still stands from v1

- **Surfaces and colour:** the black canvas and `--raised` only for floating things. Translucent hairlines. Three
  greys. The accent for selection and focus only. Data colours with their shapes.
- **Type:** Geist and Geist Mono, weights 400 and 500. The mono label style (11px, uppercase, +0.04em) is now used
  mainly for caption lines.
- **Controls:** one top bar; buttons are primary, secondary and quiet; radii 4, 8 and 12; 44px tap targets on
  touch.
- **Wording:** "Priority", never "Score". "Probably not a planet", never "fake". Vote counts appear after you vote.
  "Candidate", never "discovered". No game language, no em dashes, no developer copy.
- **Charts:** they sit on the canvas (or a `--well`) and their labels render at 1:1. The user's own guess is a
  dashed line.

## What changes from v1

| v1 said | v2 says | Why |
|---|---|---|
| Top bar: Sky map · Lab · Finder | **Events · Sky · Lab · Finder** | Events get their own image-first home; the sky becomes secondary |
| Sections are ruled text with tables | **Sections are picture grids**, each with a heading and at most one short line | The owner's rule: fewer words, far more pictures |
| Captions: source line plus a sentence | **One mono caption line only**; sentences move behind **i** | Word budget |
| Famous stars as a table | **Famous stars as survey photographs** of their fields | A table is text; the stars can be seen |
| Section rhythm 48 / 64–96px | **160px** on landing surfaces, **96px** on app pages | "More air" |
| Container 1200, margin 40 | **Container 1312, margin 64** (40/32/20 below) | Pictures want width; margins want air |
| Display 56px | **Display clamp(40px, 5.6vw, 80px)**, one statement of 12 words or fewer, on the hero photograph | One confident sentence over one picture |
| "The sky is pure black" | **The page is `#000`; the full sky is ESO's real photograph** (eso0932a) on that black | The owner asked for a real all-sky photograph; it is dark, real, and makes positions legible |

## Conflicts with the high-end-visual-design skill, and my recommendation

| The skill says | Recommendation | Why |
|---|---|---|
| "Double-bezel" nested shells around every card and image | **No.** Pictures sit flat on black, 4px radius, no frame | Shells are decoration; a real photograph needs no tray. DESIGN.md: flat, no nested surfaces. |
| Glass blur and radial mesh gradients | **No** | DESIGN.md bans glows and gradient washes. A picture is the only colour field. |
| Pill CTAs with an icon in a nested circle | **No.** 8px buttons, arrows inline | Our buttons sit beside inputs and filter chips; one control radius. |
| Eyebrow pill above every H1/H2 | **No** | The same scaffold impeccable bans; our mono line is a caption for data, not a kicker. |
| Rotated, overlapping "Z-axis" cards | **No** | Scientific pictures are not collage material; rotation implies play. |
| Floating "island" nav, no edge-to-edge sticky bar | **Keep the edge-to-edge bar** (transparent over the hero, `#000` elsewhere) | The same bar must sit above the full sky and the map; a pill would float over data. |
| Scroll reveals with blur | **Not specified here.** Motion belongs to the Motion section (another session) | Out of scope for POLISH. |
| Macro-whitespace, `py-24` to `py-40` for sections | **Yes: 96 to 160px** | This is the owner's "more air". |
| Asymmetric bento and editorial split layouts | **Yes:** a bento for home's "This week", an editorial split on event detail and the candidate report | Breaks the identical-grid monotony without decoration. |
| Custom easing, GPU-safe properties, blur only on fixed layers, mobile single-column collapse | **Yes** | Compatible with DESIGN.md. |
| Banned fonts include Inter; premium grotesk assumed | Already Geist | No change. |

## Word budgets (hard numbers)

| Surface | Budget | v2 mock |
|---|---|---|
| Home hero | **≤ 12 words**, one sentence, no lede | 7: "The sky this week, in real pictures." |
| Any section on a landing surface (home, /lab, /finder, /events) | a heading of **≤ 3 words** plus **≤ 1 line of ≤ 8 words** | e.g. "Candidates" / "Dips in starlight, waiting for your eye." |
| Paragraphs on a landing surface | **0** | 0 |
| Picture caption line | **1 line, ≤ 8 mono tokens**: source · date or time · flag | "DESI Legacy Surveys · archive" |
| Tile | a name (**≤ 4 words**) plus the caption line | "SN 2026abvs (SN IIn)" / "Archive" |
| Event detail, visible | title, one mono line, **3 facts**, two actions | 61 words on the whole page |
| Science page (candidate report, lab experiment), visible | title, **one line of ≤ 12 words**, ≤ 4 facts; everything else in drawers | 115 words on the whole report |
| Drawer summary | **≤ 3 words** plus a mono state ("6 of 6 passed") | "Checks · 6 of 6 passed" |

### Measured words per page

All visible text on the full page, nav included. Not counted: closed drawers, **i** popovers, and chart and map
labels (given separately as +n). Counted in Chromium at 1440 on 26 Sep 2026.

| Page | Today (app) | v1 mock | **v2 mock** |
|---|---|---|---|
| Home `/` | 676 | 518 | **176** |
| Events (today `/map` feed, v2 `/events`) | 529 | n/a | **255** (41 tiles) |
| Event detail `/events/[id]` | n/a (a map panel) | n/a | **61** (+2) |
| Sky `/sky` | (in `/map`) | n/a | **20** (+24 constellation names) |
| Lab `/lab` | 170 | n/a | **78** |
| Finder `/finder` | 432 | n/a | **148** (14 tiles) |
| Candidate `/finder/[id]` | 788 (+24) | 716 (+22) | **115** (+22) |

## Spacing (err on the side of air)

- **Scale** (4px base): 4, 8, 12, 16, 24, 32, 48, 64, 96, **128, 160**.
- **Section padding**, top of each section:
  - landing surfaces: **160** (≥1024), **128** (640 to 1023), **96** (<640);
  - app pages: **96 / 80 / 64**;
  - the last section on a page has the same padding at the bottom.
- **Section head to content: 40.** Heading to its line: **8**.
- **Page margins: 64** (≥1280), **40** (1024 to 1279), **32** (640 to 1023), **20** (<640).
  Content max **1312**. Reading measure **560**.
- **Picture grids:**
  - column gap **24** (12 on phones), row gap **40** (28 on phones);
  - candidate grid rows **56**;
  - lab grid rows **64**.
- **Around a picture:** image to name **12**; name to caption line **2**; caption line height **20**.
- **Editorial split:** gap **96** between the picture and the side column (48 when stacked).
- **Top bar: 64** (56 on phones).

## Image system

### What we may use

| Source | What | Licence | Credit line (exact) | Notes |
|---|---|---|---|---|
| NASA Image and Video Library (images.nasa.gov) | mission photographs, instrument images (for example Kepler first light, PIA11984) | Mostly public domain | "NASA/Ames/JPL-Caltech" (the item's own `center` or `secondary_creator`) | Check each item's metadata for third-party copyright; never imply endorsement; skip artist's concepts |
| SDO via Helioviewer (api.helioviewer.org) and sdo.gsfc.nasa.gov | the Sun at the event's time (AIA 131, 171 and 193 Å) | Not copyrighted (NASA SDO image-use rules) | "NASA/SDO and the AIA, EVE, and HMI science teams; Helioviewer.org" | Take the frame nearest `observed_at`; say "2 min before" when it isn't exact |
| ESA/Webb (esawebb.org) | Webb images | CC BY 4.0 | as on the page, e.g. "NASA, ESA, CSA, and STScI" | Only `weic` or `potm` photographs, not artist's impressions (`ann…` with "Artist's") |
| ESA/Hubble (esahubble.org) | Hubble images | CC BY 4.0 | as on the page, e.g. "NASA, ESA, and S. Beckwith (STScI) and the HUDF Team" | Same rule |
| ESO (eso.org) | photographs from ESO sites; eso0932a | CC BY 4.0 | "ESO/S. Brunier", "ESO/Y. Beletsky" | Skip `ann…` artist's impressions |
| NOIRLab (noirlab.edu) | Rubin First Look, Gemini, Kitt Peak | CC BY 4.0 | "NSF–DOE Vera C. Rubin Observatory/NOIRLab/SLAC/AURA" | Its storage refuses non-browser downloads; fetch the file linked from the image page |
| ESA/Gaia | Gaia sky maps | **CC BY-SA 3.0 IGO** | "ESA/Gaia/DPAC" | Share-alike: our crops of it must carry the same licence; not used yet |
| hips2fits cutouts (CDS) | DESI Legacy DR10, then Pan-STARRS DR1, then SkyMapper DR1, then DSS2 | Survey terms (acknowledgement required); HiPS ODbL-1.0 (CDS) | as in `credits.json` | Reject blank (outside the footprint) and one-band false-colour cutouts automatically; always marked **archive** |
| Rubin alert stamps | the event's own Rubin cutout | no licence stated by the source | "Rubin Observatory alert stamp" | Show as the event's own image, not archive |
| Our renders | light curves, pixel maps, charts | follows the data (TESS is public domain) | "NASA TESS via MAST; rendered by Planet Hunter" | Drawn only from real data, or tagged DEMO |

**Never:**
- generated or AI images;
- artist's impressions presented as photographs;
- stock "space" art;
- tinted or duotoned photographs;
- text burned into our crops.

### Storage and credits

- Files live in `web/public/images/{sky,feature,events,stars,data}/`: JPEG, up to 2400px (4000 for the sky
  panorama), quality 82 to 86, progressive.
- `credits.json` is keyed by path, with
  `{ url, title, credit, licence, source, width, height, file?, archive?, event?, note? }`.
  The **i** on every picture reads from it. A `/credits` page lists them all.
- Fetching is scripted: one entry per picture, with its licence, recorded as it is saved.

### Crop and size rules

- **Hero:** one full-bleed photograph, 100vh up to 920px, `object-fit: cover`. The object sits on a third, and
  the display line sits in the photograph's own dark negative space (White Desert).
  - Only the page title may sit on a photograph.
  - The caption line goes **under** the photograph, never on it.
- **Astronomical objects** (the Sun, planets, galaxies): never crop through the object unless the viewport edge
  cuts a planet deliberately (Claude on Mars). Otherwise whole, centred, on black (Sanctuary).
- **Tiles:** 1:1 in grids, 3:4 for lab portraits, 4:3 for lab landscapes. `cover`, 4px radius, no border, no
  overlay. Survey cutouts are centred on the target with a field of 3′ (events) or 7′ (stars).
- **Home bento:** one 2 × 2 picture plus 4 small, then a full row of 4.
- **Grids:** 5 columns ≥1280, 4 ≥1024, 3 ≥640, 2 on phones. No gutterless mosaics (Archivo), since names sit
  under pictures, not on them.
- **Data as picture** (Meteo): light curves and pixel maps render large, on `--well` or black, labels at 1:1,
  with a caption line like a photograph.
- **Where the black sky meets a picture:** a picture never has a frame or glow. Its black is our black; photographs
  with their own black (SDO, Webb) blend into the page. Survey cutouts keep their own sky background at 4px radius.

### No picture? A typographic tile

When an event has no image and no precise position (error ≥ 0.01°), and is not solar, it gets a typographic tile
instead: a 1:1 `--well` square with a 1px `--line` border.
- Inside: its category shape at 22px, its name at 20/24, and "TYPE · DATE" in the label style.
- This covers NEOs, comets, GRBs with wide error circles, fireballs and storms without an SDO frame.
- A survey cutout would claim a precision we don't have, and a generated image would be fake.

## Where the text goes

- **The caption line** (the one line every picture has): source · date or time · flag, in the mono label style.
  - Flags: `archive` (taken years before the event), `guess 82%` (machine classification), `candidate`,
    `demo`.
  - Truncates with an ellipsis on phones; the full text is in the **i**.
- **The i button**, at the right end of the caption line: a 20px ring. It opens a `--raised` popover with the
  title, credit, licence, a source link and the one honesty sentence ("The supernova itself is not in this
  picture; its host galaxy is.").
- **Hover (desktop):** a tile's full type name is its `title`. Hover never carries anything a touch user
  can't reach with the **i**.
- **Drawers** (`<details>`, closed by default): one per explanation, a summary of ≤ 3 words plus a mono state,
  a + / − marker, a 56px row.
  - Candidate report: Checks, Pixel check, Known lists, Priority, What a candidate is.
  - Event: How we know, About the picture.
  - Home: How we stay honest, Credits.
- **Science pages:** the chart or picture leads, and the explanations are all in drawers. The candidate report
  opens with the star's field and the folded dip side by side. Its text is one line: "A dip every 3.81 days. A
  candidate, not a planet."
- **Honesty is never more than one tap away:**
  - "archive" and "guess" are in the caption line itself;
  - "candidate" is in the line under the title;
  - "demo" is a tag next to the title.

## Events: from 3D sky to gallery

### Routes

| Route | What | Notes |
|---|---|---|
| `/` | Home | Hero photograph → This week (bento, links to `/events/[id]`) → Candidates → Lab → Famous stars → drawers |
| **`/events`** | The gallery, newest first, grouped by UTC day ("Today", "Yesterday", "23 Sep") | **The same filter bar and URL params as MAPUI**: `time`, `from`, `to`, `types`, `src`, `conf`, `pics`, `rubin`, with defaults unchanged, so `/events?types=transients&time=30d` works as it does on the map today |
| **`/events/[id]`** | Event detail | The id is the contract id, URL-encoded (`tns%3A2026abvs`) |
| **`/sky`** | The full-screen sky | The existing 3D sky, with ESO's eso0932a as its background sphere and faint constellations. `?event=<id>` flies to an event; filter params as above |
| `/map` | Redirect | 308 to `/sky`, keeping the query |
| `/credits` | Every picture's credit | Rendered from `credits.json` |

Pictures / Sky is a two-option toggle in both headers. The same filters carry across, so switching views never
loses the selection.

### Gallery tile

- **The picture, in priority order:** the event's own image; a survey cutout of the field when the position error
  is under 0.01°; an SDO frame for solar events; otherwise the typographic tile.
- **Under it:** the category shape plus a short name, then the caption line flag (`Archive`, `Guess 82%` or the UTC
  time).

### Event detail

- **Editorial split:** the picture on the left, 7/11 of the width, 1:1, with its caption line. The side column is
  sticky.
- **Side column:**
  - the kind label ("Supernova · type IIn");
  - h1 name;
  - a mono line (date, time · source · basis);
  - three facts: **Reported**, **In** (the IAU constellation, from its boundaries), **Position**;
  - the **compact sky**;
  - Open in sky (secondary) and the source link (quiet).
- Drawers below.

### Compact sky ("where is it")

A 56° × 34° crop of eso0932a around the event:
- in galactic orientation, so the Milky Way runs horizontally;
- constellation lines at 35% and names in the label style;
- the event as its category shape at 32px, with a 2px black separation.

It answers "in Orion, near the Milky Way" at a glance. Caption line: "Where it is · ESO/S. Brunier".

### Full sky

- eso0932a, equirectangular in galactic coordinates (verified against the LMC, SMC, M31, M42 and Carina).
- Constellation lines at 22% and names of the major constellations, from d3-celestial (BSD-3-Clause). Events are
  their category shapes.
- In the 3D sky the same image is the celestial sphere's texture, rotated from galactic to ICRS.
- On phones the flat view is a pannable 1100px strip.
- **MAPUI owns the implementation;** this is the spec it receives.

## Page by page

- **Home:**
  - the hero is eso0733a (the VLT laser towards the Milky Way's centre);
  - This week is a 9-picture bento;
  - Candidates are 6 survey fields with the dip as a sparkline;
  - Lab is 4 portrait pictures;
  - Famous stars are 4 survey fields;
  - honesty and credits go in drawers.
- **/events:** the gallery above. The v1 feed column goes away.
- **/events/[id]:** the editorial split with the compact sky.
- **/sky:** the photograph plus constellations. The filter bar sits on top, the caption line underneath.
- **/lab:**
  - the hero is Webb's Cosmic Cliffs, with the display word "Lab" and one line;
  - 4 experiments at 4:3, each with a real picture: NGC 3603 for colour and temperature, WASP-18's TESS pixels
    for "Hear a star", the Hubble Ultra Deep Field for the Hubble diagram, SDO 131 Å (light from one iron line)
    for chemical fingerprints;
  - Star labs are the famous-star fields;
  - one drawer.
- **/finder:**
  - title plus one line, and the funnel as one mono line;
  - a grid of 14 survey fields, each with its folded dip underneath and one caption line;
  - two drawers.
- **/finder/[id]:**
  - the field and the dip lead side by side;
  - title, one line, 4 facts, the vote (counts after voting);
  - the whole light curve full-width;
  - the pixels with "95% on target";
  - five drawers.

## Top 10 changes (the order to build)

1. **`/events` gallery** with the MAPUI filter bar and params, plus **`/events/[id]`** with the compact sky.
2. **`web/public/images/` and `credits.json`**, plus a fetch script with the survey fallback and the automatic
   blank and false-colour rejection.
3. **The caption line plus i** component, used by every picture.
4. **Drawers** for every explanation; science pages collapse by default.
5. **Home rebuilt around pictures**, within the word budgets (≤ 12-word hero, 0 paragraphs).
6. **`/sky` on eso0932a** with constellation lines and names (MAPUI), and `/map` redirecting to `/sky`.
7. **The typographic tile** for events with no picture.
8. **Spacing to the v2 scale:** 160 / 96 section padding, 64 margins, a 1312 container.
9. **Lab and Finder as picture grids**: survey fields for stars and candidates, real pictures for experiments.
10. **The top bar becomes Events · Sky · Lab · Finder.** Everything else from v1 (tokens, controls, wording)
    carries over.

# References v2: image-led

Browsed on Awwwards, 26 Sep 2026: the Photography and Photographic tags, Big Background Images, Fullscreen,
Gallery, Institutions, Minimal (page 2), and searches for museum, telescope, photography archive, planet and earth.
Every site below has an Awwwards entry. Each has `-hero.jpg` (first screen, 1440 × 900) and `-scroll.jpg` (after
about 1,300px). Where the hidden text is the point, there is also `-hover.jpg` or `-open.jpg`.

Word counts are visible words in the first screen, counted from the capture; nav and consent banners are excluded.

Rejected:
- Quanta's "How we came to know Earth": scroll-locked behind a consent wall; the imagery never loads.
- UN "Race to save space": a sound wall.
- nasaspacecraft.com: a parked domain.
- Distance to Mars: a cartoon Earth.
- Agency showreels and wedding portfolios.

---

## 01 White Desert (white-desert.com). Awwwards: Site of the Day

Antarctic expeditions. The first screen is one photograph, a penguin at 1440 × 900 `object-fit: cover`, with
the word ANTARCTICA over its lower third.

- **Images**: full-bleed, one per viewport, always `cover`. The crop puts the subject on a third and leaves the
  sky or ice as negative space for the word.
- **Text on the first screen**: 1 display word plus a 9-word italic line and 2 buttons (**about 13 words**).
- **Where the text hides**: the story sits beside the next photograph as one narrow 110-word column (about 280px),
  and "How it works" is a drawer on a tab at the right edge.
- **Take**: one picture per screen; the word sits in the picture's own negative space; the explanation goes in a
  side drawer.
- **Avoid**: 190px condensed display type (our voice is Geist), the orange drawer tab.

## 02 Project Aperture (project-aperture.com). Awwwards: in Photography archive

A travel photographer on a near-black `#211D20` page. Five tall 60 × 170px slivers sit centred in 1440px of dark.

- **Images**: tiny, cropped to extreme 1:3 portrait slivers, placed in a row. The page is about 92% empty.
- **Text**: "TRAVEL PHOTOGRAPHY · 2023–2026" as an 8px mono line, plus IDC · LI · ABOUT (**6 words**).
- **Where the text hides**: behind ABOUT; each sliver opens its set.
- **Take**: generous emptiness makes small real images precious; slivers as an index; a single mono line as the
  only caption.
- **Avoid**: text that small (8px); duotone tinting of the photos (it alters the data colour of our images).

## 03 Index Georgia (index-georgia.com). Awwwards: in Photography archive

An archive of Georgian street art. One 1192 × 568 photograph, a two-line caption under its left edge, then a
4-up grid of 280 × 220 crops.

- **Images**: one large lead at about 83% width (4:2 crop), then a strict grid of identical 280 × 220 `cover`
  crops.
- **Text**: "Archive of selected Georgian street art works. 2021–2023." (**8 words**), set in 11px under the
  picture.
- **Where the text hides**: "About project" in the corner. The long essay starts only after the grid, in narrow
  200px columns.
- **Take**: the caption is under the picture, left-aligned to its edge, small, and ends with the date; the lead
  image, then the grid; the essay comes last and is optional.
- **Avoid**: the white page.

## 04 Windows (wndws.space). Awwwards: in Photography and Minimal

A world of windows. A 13 × 6 grid of 44 × 64 portrait slots, each empty or holding a photograph.

- **Images**: every picture is the same 2:3 portrait crop, very small, in a grid with as much space as picture.
  Empty slots are drawn as faint outlines, so the grid reads as an instrument, not a collage.
- **Text**: the wordmark plus "60 windows · 41 places · 24 countries" (**7 words**).
- **Where the text hides**: on **hover**, a tiny label with the person's name and place appears beside the
  thumbnail (`04-windows-hover.jpg`). On **click**, the photo opens at 180 × 310 with one italic sentence, the
  name, the place and a handle (`04-windows-open.jpg`).
- **Take**: hover shows name and place, click shows the one sentence; empty slots count as data; the counts line
  as the only headline.
- **Avoid**: the grey page, the italic serif.

## 05 Archivo Canarias (archivocanarias.com). Awwwards: in Photography archive

An archive of Canarian artists. A 3-column grid of 463 × 494 cards with names laid over the image's lower-left
corner.

- **Images**: large near-square crops (about 0.94:1), three per row with 4px gutters, filling about 94% of the
  viewport once scrolled.
- **Text per image**: the name in 32px plus 3 to 5 tag chips (**4 to 8 words**). There is almost no page copy.
- **Where the text hides**: a "+" in each image's corner opens the record. There is also a tag index and a map.
- **Take**: dense, almost gutterless grids work when every tile is a real image; a single "+" is the only
  affordance.
- **Avoid**: names over images (it breaks our "no text over pictures" rule and hurts contrast on bright
  frames), the pill tags.

## 06 Sanctuary on the Moon (sanctuaryonthemoon.com). Awwwards: in Space

A disc of human knowledge bound for the Moon. A real photograph of the Moon, about 520px, centred on dark navy,
with the wordmark and one line across it.

- **Images**: one astronomical photograph, not cropped: the whole disc floats in space. This is exactly how our
  SDO Sun images and Webb or Hubble frames can sit on `#000`.
- **Text**: the wordmark plus "A testimony to our humanity, ready to reach the Moon in 2030." (**12 words**).
- **Where the text hides**: in the section pages; audio behind a mute toggle.
- **Take**: an uncropped astronomical object on black; a 12-word hero.
- **Avoid**: the navy tint, the drawn hexagon over the photo, the 8-item nav.

## 07 Simply 3D Meteo History (meteo.ashwyn.studio). Awwwards: in Data visualisation, Earth

Decades of weather drawn as a 3D bar field on `#000`.

- **Images**: the data **is** the picture, centred at about 40% of the viewport on pure black.
- **Text**: a place name, a region and a status pill (**about 9 words**), plus "Data: Open-Meteo & OpenStreetMap" at
  the foot.
- **Where the text hides**: controls in small pills at the bottom-left; the source is one line at the bottom-right.
- **Take**: our light curves and pixel heatmaps can be the image, on black, as large as a photograph, with one
  source line.
- **Avoid**: the teal UI accent.

## 08 Claude on Mars (anthropic.com/features/claude-on-mars). Awwwards: "Claude on Mars" (carried from v1)

A real Mars mosaic, 1150px wide, rising from the bottom of a black first screen under a 4-word title.

- **Images**: the planet is cropped by the bottom edge, so it reads as rising; `contain` inside a square box.
- **Text**: "Four hundred meters on Mars" (**5 words**). Captions later are mono uppercase with date and sol.
- **Where the text hides**: the story is below the fold in a 640px column, and each rover image has a mono caption.
- **Take**: a planet cropped by the viewport edge; a 5-word title; mono date captions.
- **Avoid**: the serif.

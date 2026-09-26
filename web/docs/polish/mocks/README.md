# Mocks: before and after

Static HTML, no build step. `polish.css` holds the proposed tokens and primitives (see DIRECTION.md); each page adds
only its own composition. Serve the folder (`python3 -m http.server` inside `mocks/`) and open `home.html` or
`finder-id.html`. Fonts load from Google Fonts (Geist, Geist Mono).

Content is real: the six event pictures in `assets/` are the thumbnails from `public/data/events.mock.json`
(NASA SDO, DESI Legacy Surveys via CDS hips2fits), `assets/hero-sky.png` is a capture of the current HeroSky
render, and the candidate report's charts and pixel images are drawn from `public/data/finder/c/tic219345170-01.json`.

| Page | Before | After |
|---|---|---|
| Home, 1440 | `shots/home-before-1440.png` | `shots/home-after-1440.png` |
| Home, 390 | `shots/home-before-390.png` | `shots/home-after-390.png` |
| /finder/[id], 1440 | `shots/finder-id-before-1440.png` | `shots/finder-id-after-1440.png` |
| /finder/[id], 390 | `shots/finder-id-before-390.png` | `shots/finder-id-after-390.png` |

Full-page captures at a 1440 × 900 and 390 × 844 viewport (the 390 captures are 375 wide because Chromium draws
a 15px scrollbar). In the "after" captures, sticky elements are set to static so the full-page image is not
smeared; in the browser the top bar and the vote panel are sticky.

What the mocks demonstrate, and what they leave out:

- Home: one black canvas, the week's counts as the hero's floor, captioned picture tiles with the archive caveat
  said once, ruled line-art doors, famous stars as a table, the shared top bar.
- /finder/[id]: the shared top bar, the page-header pattern with a summary tag row, a ruled fact grid, charts on
  the canvas at 1:1 label size, checks as a table, neutral status, "Priority", vote counts hidden until voting,
  the vote panel after the facts on phones.
- Not mocked: interaction states beyond hover, the star search popover, the post-vote state, loading and error
  states (specified in DIRECTION.md).

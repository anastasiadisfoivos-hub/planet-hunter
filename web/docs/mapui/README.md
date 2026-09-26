# Sky map filters and motion (MAPUI)

The left filter sidebar is gone. Filters float over the sky (top left), map layers have their own
button (bottom left), and filter changes move instead of popping.

## What the map does now

- **Filter bar:** `24 h | 7 d | 30 d`, six category chips (marker glyph, count for the current range,
  `aria-pressed` on / off / mixed, dimmed at zero but still clickable), **More** with a badge for
  non-default settings inside it, and **Reset** when anything differs from the defaults.
- **More:** event sub-types, sources, minimum confidence, only with pictures, custom date range, and
  Rubin's latest nights. It is a popover on desktop and a bottom sheet on phones.
- **Layers:** Stars (bright, dim, planet hosts), Overlays (Rubin coverage, Rubin heatmap, Milky Way
  & nebulae), Scale (compressed / true).
- **Empty feed:** "No events match these filters" and a **Clear filters** button.
- **Phone (390 px):** time and chips are one sideways-scrolling row; More and Layers are bottom
  sheets. Nothing covers the sky until you open something.
- **Keyboard:** every control is reachable with Tab. Esc closes a popover or sheet and returns focus
  to its button, and Tab-ing out of one closes it. The focus ring is the 2px accent.
- "About this map" (star colours, Rubin footprint source) moved into the **About the data** popover.

### Filters in the URL

Filters are written to the address bar, so a filtered view can be shared. Only non-default settings
are written, so an unfiltered map keeps a clean URL. `host`, `bright`, `fps` and `nodetail` work
exactly as before.

| Param | Meaning |
|---|---|
| `time=24h\|30d\|custom` | time range (7 d is the default and is not written) |
| `from=YYYY-MM-DD&to=YYYY-MM-DD` | custom range, with `time=custom` |
| `types=transients,comet` | a whole category by its key, otherwise single types; `none` for nothing |
| `src=ztf,tns` | sources |
| `conf=40` | minimum confidence, percent |
| `pics=1` / `rubin=1` | only with pictures / Rubin's latest nights |

## Motion

All motion is CSS transitions, except two small pieces of hand-written JS: FLIP for the feed
(`motion.ts`) and the marker fade (`scene/markerFade.ts`, a shader attribute).

| What | How | Time |
|---|---|---|
| Event markers | fade in and out (opacity); markers that leave cannot be picked | 240 ms |
| Counts (chips, feed, Feed tab, status bar) | roll up or down to the new value | 200 ms |
| More, Layers, About the data | grow from the button that opened them (`transform-origin`) | 240 ms in, 160 ms out |
| Chips, time segments, bar buttons | `scale(0.97)` on press | 120 ms |
| New feed rows | fade up, 30 ms apart, 150 ms of delay at most | 200 ms |
| Rows that stay | FLIP to their new place | 200 ms |

Under `prefers-reduced-motion` every duration and delay is 0 and FLIP is skipped. While the tab is
hidden, running CSS animations and FLIP are paused (`pauseWhileHidden`), and the 3D loop stops. The
marker fade then resumes where it stopped instead of jumping to the end.

## Screenshots

| File | Shows |
|---|---|
| `1440-default.png`, `390-default.png` | default view |
| `1440-chips-toggled.png`, `390-chips-toggled.png` | Transients and High energy off, 30 d |
| `1440-more-open.png`, `390-more-open.png` | More (popover on desktop, sheet on phone), badge 2 |
| `1440-layers-open.png`, `390-layers-open.png` | Layers (popover on desktop, sheet on phone) |
| `1440-empty-state.png`, `390-empty-state.png` | every category off: the one-line empty state |
| `filter-fade.gif`, `filter-fade-frames.png` | Transients off and on again: markers fade instead of popping |

The phone sheets are `390-more-open.png` and `390-layers-open.png`. The captures were taken with
Playwright's Chromium on software GL (SwiftShader), because the Playwright MCP browser was held by
another session. The GIF's frame rate is limited by software rendering, not by the animation.

See `audit.md` for the `/impeccable audit` of this page.

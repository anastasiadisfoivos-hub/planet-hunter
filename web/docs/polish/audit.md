# /impeccable audit: the built v2 site

Run 26 Sep 2026 on the production build (`next build`, `next start`). Pages: `/`, `/events`, `/events/[id]` (with and
without a picture), `/sky`, `/lab`, the four experiments, `/lab/star/100100827`, `/finder`, `/finder/[id]`,
`/finder/sensitivity` and `/credits`. Viewports: 1440 × 900, 390 × 844, and 390 × 844 with a touch pointer.

Method:
- the impeccable detector (`detect.mjs`) over `app/` and `components/`;
- in-browser checks on every page: contrast of every visible text node against its effective background, tap
  targets, horizontal overflow, heading order, alt text and accessible names;
- a network pass for failed requests and image weight.

## Score

| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 3 | No contrast failures on real text; every control named. Tap targets reach 44px on touch after fixes. |
| 2 | Performance | 3 | Responsive `next/image` with lazy loading: home 527 KB of images on first load at 1440 (164 KB on a phone). The sky panorama is 2.8 MB (desktop) or 645 KB (phone). |
| 3 | Responsive | 4 | No horizontal overflow on any page at 1440 or 390, after one fix. |
| 4 | Theming | 4 | Tokens throughout; the last raw hex values replaced. Dark only by design. |
| 5 | Anti-patterns | 4 | Detector: 0 findings. No gradient text, glass, eyebrows, nested cards or card grids of text. |
| **Total** | | **18 / 20** | **Excellent** (minor polish) |

## Findings and actions

### Fixed (DESIGN.md agrees)

| Finding | Where | Action |
|---|---|---|
| [P1] 2px horizontal overflow at 390 | `/events/[id]` facts row: the no-wrap position ("04h 52m +05° 09′") in a 3-column grid | Facts go to 2 columns on phones, with the position spanning both |
| [P1] Tap targets under 44px on touch | the Pictures/Sky switch (38px), vote options and reason chips (40px), small buttons, segmented controls, the time segments, the overlay's close button (27px) | One coarse-pointer rule per component file: all reach 44px (DESIGN.md: controls are 44px on coarse pointers) |
| [P2] Nav links narrower than 24px at 390 ("Sky" was 22px) | top bar | Links get a 44px minimum width; the icon-only wordmark 44px |
| [P2] Raw hex in components | hero backgrounds `#000`, the compact sky's separation stroke, lab link hover `#ffffff`, `themeColor #09090b` | `var(--space)` and `opacity` instead; theme colour `#000000` |
| [P2] Stale copy after the chart change | Hubble: "move the blue line" | "move your dashed line" |
| [P2] Science explanations open by default | Hubble, Thermometer, Hear a star: a long "why" section at the end | Each is a closed drawer ("Why it expands", "Why colour is heat", "Raw or folded"); the chart leads |

### Rejected or deferred (with the reason)

| Finding | Why it stays |
|---|---|
| 33 "1.00:1 contrast" hits on `/finder/sensitivity` | False positive: the heatmap cells use `color-mix(in oklab, …)` backgrounds that the checker cannot parse. The text in those cells measures at least 4.5:1 in a canvas-based check (critique, v1). |
| The i buttons measure 20 × 20 | The visible ring is 20px on purpose (a caption-line mark); a `::after` extends the hit area by 12px on every side, to 44px. |
| Checkbox inputs measure 16 × 16 in the More filters | Each sits inside a full-width label row that is the tap target (44px on touch). |
| Inline text links under 44px ("current candidates") | WCAG 2.5.8 exempts targets inside a sentence. |
| 8 × 404 on `/data/spectra/*` in the lab | By design: the lab asks for the SPECTRA session's real files first and falls back to its demo files, which it then tags DEMO DATA. The requests stop failing when SPECTRA publishes. Not a POLISH change. |
| The sky panorama is 2.8 MB on desktop | It is the whole sky at 16.7 px per degree, ESO's largest JPEG. It loads after the page, off the main thread, and phones or small GPUs get the 645 KB version. Tiling it would be the next step if needed. |
| `/lab/fingerprints` never reaches network idle | A long-lived request, not a loop (checked: one request per resource). The page renders and works. |

## Positive findings

- Every picture has alt text, a caption line and an i with its credit and licence. `/credits` lists all of them.
- Every page has exactly one h1 and no skipped heading levels; every button and link has an accessible name.
- Motion is all on `transform` and `opacity`, at 200ms or less, and all of it is off under `prefers-reduced-motion`.
- Pictures below the fold are lazy and responsive: a phone scrolling the whole home page downloads 302 KB of images.

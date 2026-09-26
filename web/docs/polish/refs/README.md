# References

Chosen from Awwwards on 26 Sep 2026 after browsing: the Minimal listing, the Dark listing and the Dark Mode
collection, the Data Visualization category, Technology filtered to dark, Sites of the Day (pages 1 to 3), and a
"space" search (Awwwards has no public "Space aesthetic" board URL any more, so the search on its
inspiration index stood in for it). Every site below has an Awwwards entry.

Filter: dark, restrained, typographic, product-grade or science. Rejected: agency showreels, scroll-jacked
stories, anything that only works with sound, light-only sites (Seasats, Mind Robotics, State of AI Design) and
loud colour (Cerebrium's magenta, Orchid's purple).

Screenshots are 1440 × 900: `NN-name-hero.png` is the first screen, `NN-name-scroll.png` is after a 1400px
scroll. Computed-style samples are in `measurements.json`.

---

## 01 Resend (resend.com). Awwwards: "Resend Launch Week VI"

Product-grade dark UI for developers: black page, hairline cards, code blocks, one white button.

Take
- **Translucent hairlines**: `1px solid rgba(214,235,253,0.19)` for card borders, `0.145` for list rows. One
  token works on pure black, on off-black and on a raised card, so hairlines never look heavier on one surface.
- **Three-grey ramp**: `#EBECED` / `#A1A4A5` / `#464A4D`. Everything is one of three.
- **14px UI, 12px floor, mono only for values**: Inter 14/20 everywhere; Commit Mono 12/16 for code and
  status values.

Avoid
- Gradient text on the section title ("Integrate *this weekend*") and the glossy 3D icon tile.
- Pill-shaped primary buttons (fine for marketing; our controls sit next to segmented controls and inputs).

## 02 Portal Space Systems (portalsystems.space). Awwwards: "Portal Space Systems"

A spacecraft company on near-black `#0D0D0D`, with a hairline line drawing of the craft as the only hero image.

Take
- **Line-art over renders**: the hero is a 1px drawing on black. The same idea fits our empty states and page
  headers (a hairline orbit or transit diagram instead of an illustration).
- **Spec triplets**: `6 km/s / delta-v`, value 16px 600 over unit label 14px 400 muted, centred in a row of three.
  A pattern for star facts (Teff, radius, distance).
- **Tight negative tracking on 32 to 40px heads**: -1.3px (about -0.035em), the same as our heading tracking.

Avoid
- The long empty black scroll between sections (content-free viewport heights).
- Inter everywhere with no mono; values lose their "instrument" read.

## 03 Claude on Mars (anthropic.com/features/claude-on-mars). Awwwards: "Claude on Mars"

A science story: pure black, one real planet photograph, a long-form column, instrument captions.

Take
- **Mono uppercase captions with date and source**: 13px, UC, +0.01em, `DEC. 8, 2025 (SOL 1707)`,
  `SUPERCAM`. Our pictures already require caption and credit; this is how to make that look intentional.
- **640px reading column with 872px figures** that break out of it.
- **Meta text and hairline share one colour** (`#87867F`), so captions and rules recede together.

Avoid
- The serif display face (a second family would split our voice; Geist stays).
- Its light `#FAF9F5` site chrome around the black story.

## 04 21 HRS on the Moon (21hrs.space). Awwwards: Site of the Day

Apollo 11 story on black with instrument framing.

Take
- **Meta pairs**: `MISSION` 10px mono UC over `Apollo 11` 18px bold; `YEAR` over `1969`. Label above value,
  left and right of a centred title.
- **Hairline rules that frame a title** (a rule either side of "21HRS ON THE").
- **Bottom index strip**: evenly spaced chapters separated by 1px verticals, mono UC 10px. A model for the lab's
  experiment index.

Avoid
- Scroll-to-land scroll-jacking, "best experienced with sound", the orange corner brackets (HUD cosplay).

## 05 Auriga Space (aurigaspace.com). Awwwards: in Technology / dark

Electromagnetic launch company; the whole UI is one mono size.

Take
- **One label style, used everywhere**: Spline Sans Mono 12px, UC, +0.01em. Nav, kickers, news ticker and
  buttons share it. Discipline worth copying for our 11px label.
- **Bracketed text actions** (`[ READ MORE ]`) as the quietest button tier.

Avoid
- The viewport-wide wordmark and the loud cyan emphasis in the headline.

## 06 Vast (vastspace.com). Awwwards: in Technology

Space-station company. Light site, but its captioning and progress UI are the best in the set.

Take
- **Captioned photos**: a small mono UC caption tag (`HAVEN-1 DOCKING ADAPTER FIT CHECK`) above a 16px
  sentence, set on the photo in a flat dark block, no blur.
- **Tick-mark progress**: a row of 1px ticks with the current one filled. Fits "step 3 of 7" in a vetting report.

Avoid
- 342px display type; the full-bleed lifestyle video.

## 07 CTAO (cta-observatory.org). Awwwards: "Cherenkov Telescope Array"

A real observatory: black hero with the Earth and particle tracks, then institutional content.

Take
- **"For Scientists" as a secondary route in the nav**: a small pill on the right. Our finder and sensitivity pages
  could sit behind a similar "Methods" affordance.
- **A real image as the hero, with nothing laid over it except one heading**.

Avoid
- Bold 48px headings (700 weight reads corporate), the blue consent wall, generic news cards.

## 08 Singularität (singularity.engl.design). Awwwards: in Culture & Education

German explainer on AGI over a starfield.

Take
- **Numbered section kickers**: `02 · BEGRIFF`, Space Mono 11px UC +0.12em, above a 56px head.
- **A vertical tick ruler on the right edge** that shows reading position. Quiet, informative, no motion needed.

Avoid
- The navy tint over the stars (our sky is black), tracking of +0.12em (too loose next to Geist Mono).

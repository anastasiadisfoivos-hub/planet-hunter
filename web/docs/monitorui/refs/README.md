# MONITOR-UI references

Collected 2026-09-26 with Playwright (1440 × 900). Six sites from Awwwards 2026 lists plus two real instrument
interfaces. For each: the one strong idea, and what makes it feel made by a person rather than generated.

## Awwwards

**01 · Where the Shadow Fell** (eclipses.bogachev.fr, Honorable Mention, 22 Aug 2026)
Idea: every solar eclipse from 2000 BCE to 3000 CE on one globe.
Human-made because: a warm paper ground (#EAE0CD) instead of black; small ochre year labels placed by hand
where they don't collide; a single timeline scrubber drawn like a ruler; instructions set in tiny mono caps
along the globe's edge ("drag to turn · scroll to zoom"). Space Grotesk + Space Mono. The data is the image.

**02 · From the Grid to the Page** (consider.digital/story, Nominee, 13 Aug 2026)
Idea: one continuous line (AC mains at 50 Hz) that the whole story rides on.
Human-made because: the line is the protagonist and is labelled like a scope trace ("alternating current ·
50 Hz") right on the line; almost-black green ground (#0C1310); a yellow mono aside that says what the page
refuses to do. No images, no web fonts. Closest in spirit to our monitor.

**03 · Every Day Is a Gift** (everydaygift.polimata.mx, Nominee, 6 Sep 2026)
Idea: a data physicalization of recovery after a break-up.
Human-made because: an odd, specific colour (pale acid yellow-green) and a condensed display face at a size
that breaks the grid; the date line "Today is September 26, 2026" at the top, as a diary would.

**04 · Radio Garden** (radio.garden, Honorable Mention 2016; screenshot only showed its start gate)
Idea: rotate the globe, hear live radio from where you point.
Human-made because: one verb, one object. Everything else is chrome that disappears. The live thing is really
live, and the interface says where it is and what's playing, never more.

**05 · The Robot and Me** (therobotand.me, Nominee, 19 Sep 2026)
Idea: seven experiments, each its own world, bound by one frame.
Human-made because: a hairline frame with a small title bar (like a lab notebook's page header), one saturated
ultramarine and a heavy grotesk; Source Serif 4 for the long reading. Confident scale jumps.

**06 · teenage engineering** (teenage.engineering)
Idea: a product company that writes its site like the front panel of its instruments.
Human-made because: nav items drawn as pictograms with tiny three-line captions; custom type (te-20/te-40);
illustration by an actual hand; labels like hardware silkscreen. Instrument vocabulary without skeuomorphism.

## Real instruments

**07 · Raspberry Shake DataView, helicorder** (dataview.raspberryshake.org, station R50D6, EHZ, live)
Idea: 24 hours of ground motion as stacked 30-minute lines, a drum recorder on screen.
What to take: one long signal folded into rows so a day fits one view; local and UTC time both labelled on
the edges; the "Real Time" state in green next to the sample rate (100 sps). Honest units on the axes.
We borrow the fold for /log: every star searched is one row, oldest at the top.

**09 · PhysioNet LightWAVE, ECG** (physionet.org/lightwave, MIT-BIH record 100)
Idea: the ECG paper grid. Major and minor divisions in pink, the trace in black, beat annotations above.
What to take: annotations sit on their own lane above the trace, tied to the moment with a thin vertical
tick, never covering the line. Our detections get the same treatment.

## What we take overall

1. One line, labelled like an instrument trace, is the hero. No hero photograph.
2. A warm or tinted ground instead of pure black; one saturated signal colour.
3. Small, precise labels on the edges (time, units, state) in a mono face, the way a chart recorder prints.
4. State is said in words ("Real Time", "live", "replay"), never implied by animation.
5. Annotations on their own lane with a tick to the moment (ECG), long records folded into rows (helicorder).

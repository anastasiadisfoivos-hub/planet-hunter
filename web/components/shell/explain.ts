// Each screen's "what you're looking at" strip (DESIGN.md v3: The explainer strip): 3 or 4 icons, two-word labels,
// one sentence each. No React and no "@/" value imports, so node --test can load it directly.

import type { ExplainItem } from "./Explainer";

export const EXPLAIN: Record<string, ExplainItem[]> = {
  monitor: [
    { icon: "star", label: "This star", tip: "The star being searched, by its TESS Input Catalog number; its colour is its temperature." },
    { icon: "trace", label: "Its brightness", tip: "Its real TESS light curve, drawn as it is read: 1.000 is its usual brightness, time runs to the right." },
    { icon: "pen", label: "Dips found", tip: "The pen marks each dip the search found: red kept as a candidate, blue already known, hollow rejected." },
    { icon: "clock", label: "When observed", tip: "When TESS took the data; the search ran later, and the box on the right says live or replay." },
  ],
  candidates: [
    { icon: "check", label: "Kept signals", tip: "A candidate is a repeating dip that passed every check the search runs, not a confirmed planet." },
    { icon: "pixels", label: "Pixel check", tip: "Which star in the TESS pixels the light really went missing from: the target, or a neighbour." },
    { icon: "catalogue", label: "Known lists", tip: "Signals already on a list of planets, TESS Objects of Interest or eclipsing binaries are filed as known, not as candidates." },
    { icon: "vote", label: "Your vote", tip: "Say whether a dip looks like a planet to you; you see how others voted only after you vote." },
  ],
  dossier: [
    { icon: "trace", label: "The dip", tip: "Every dip stacked on one period and averaged, and the whole light curve with each dip's place marked." },
    { icon: "check", label: "The checks", tip: "Each test the search runs before it keeps a signal, in the search's own words." },
    { icon: "pixels", label: "The pixels", tip: "Which star in the TESS pixels the light really went missing from." },
    { icon: "catalogue", label: "Vetting", tip: "Gaia, variable-star catalogues, LEO and TRICERATOPS check whether something else could fake the dip." },
  ],
  log: [
    { icon: "star", label: "Each star", tip: "Every star the search has looked at, newest at the top, coloured by its temperature." },
    { icon: "sky", label: "Where searched", tip: "The whole sky, flattened: where each star is, with the Milky Way, the ecliptic and TESS's latest footprints." },
    { icon: "trace", label: "Whole curve", tip: "Each row's line is the star's entire TESS light curve; dips show as spikes downward." },
    { icon: "pen", label: "What happened", tip: "What the search made of it: rejected, already known, or kept as a candidate, with the reason." },
  ],
  methods: [
    { icon: "step", label: "In order", tip: "The steps below run in this order, from a star's light to a candidate." },
    { icon: "check", label: "Each check", tip: "Every test a signal must pass before it is kept, and why." },
    { icon: "limits", label: "Its limits", tip: "What the search cannot find, measured by hiding fake planets in real data." },
    { icon: "honesty", label: "Candidate only", tip: "Nothing here is called a discovery: a candidate needs astronomers to confirm it." },
  ],
  sensitivity: [
    { icon: "limits", label: "Hidden planets", tip: "Fake planets of known size and period were hidden in the real light curves of quiet stars." },
    { icon: "check", label: "Found again", tip: "Each square is the share the search found and would have kept as candidates." },
    { icon: "star", label: "Quiet stars", tip: "Stars whose own search found nothing, so a found dip can only be the hidden one." },
  ],
};

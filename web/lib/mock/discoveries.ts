// DEMO DATA: contract-shaped Discovery records for mock mode. None of these are real detections.

import type { CatchType, Discovery } from "@/lib/contract";

/** A small inline SVG stand-in for an image cutout, so pages render without a backend. */
function cutout(kind: "before" | "now" | "difference", seed: number): string {
  const spot = kind === "before" ? 0 : kind === "now" ? 0.9 : 1;
  const bg = kind === "difference" ? "#0b0b0d" : "#101114";
  const dots = Array.from({ length: 14 }, (_, i) => {
    const x = ((seed * 37 + i * 53) % 90) + 5;
    const y = ((seed * 17 + i * 71) % 90) + 5;
    const r = 0.6 + ((i * seed) % 5) * 0.3;
    return kind === "difference" ? "" : `<circle cx="${x}" cy="${y}" r="${r}" fill="#8b909a"/>`;
  }).join("");
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect width="100" height="100" fill="${bg}"/>${dots}<circle cx="50" cy="50" r="${2.5 * spot}" fill="#f4f4f5" opacity="${spot}"/><text x="4" y="96" font-family="monospace" font-size="7" fill="#737883">DEMO ${kind.toUpperCase()}</text></svg>`;
  return `data:image/svg+xml;utf8,${encodeURIComponent(svg)}`;
}

function make(
  i: number,
  type: CatchType,
  confidence: number,
  source: Discovery["source"],
  ra: number,
  dec: number,
  detectedAt: string,
  known: Discovery["known_status"],
  explanation: string,
  name: string | null = null,
): Discovery {
  return {
    id: `demo-${String(i).padStart(4, "0")}`,
    type,
    confidence,
    source,
    origin: source === "rubin" ? "demo: Rubin alert stream (mock)" : "demo: TESS full-frame images (mock)",
    ra_deg: ra,
    dec_deg: dec,
    detected_at: detectedAt,
    name_if_known: name,
    known_status: known,
    cutouts: { before: cutout("before", i), now: cutout("now", i), difference: cutout("difference", i) },
    explanation,
    links: [{ label: "About demo data", url: "https://exoplanetarchive.ipac.caltech.edu/" }],
    raw: { demo: true },
  };
}

export const MOCK_DISCOVERIES: Discovery[] = [
  make(1, "supernova", 0.72, "rubin", 52.31, -27.84, "2026-09-24T05:12:40Z", "not_on_lists",
    "A point of light brightened next to a faint galaxy between two visits eight nights apart. That pattern is typical of a supernova, but it has not been checked by a spectrum."),
  make(2, "asteroid", 0.94, "rubin", 3.82, 1.15, "2026-09-24T03:41:05Z", "known",
    "Moved between the two paired visits 33 minutes apart, along the ecliptic. It matches a known asteroid's predicted position.", "(demo) 2019 QX4"),
  make(3, "variable_star", 0.81, "tess", 271.2, -29.6, "2026-09-22T11:00:00Z", "known",
    "Brightness rises and falls on a steady cycle. The star is already listed as variable."),
  make(4, "microlensing", 0.46, "rubin", 268.9, -30.2, "2026-09-23T02:18:51Z", "unchecked",
    "A star toward the galactic bulge brightened smoothly and symmetrically. That can mean a foreground object bent its light, but there are too few points yet to be sure."),
  make(5, "eclipsing_binary", 0.88, "tess", 84.1, -65.4, "2026-09-21T08:30:00Z", "not_on_lists",
    "Regular, sharp dips in brightness, with alternating depths: most likely two stars eclipsing each other."),
  make(6, "planet_candidate", 0.38, "tess", 95.7, -58.9, "2026-09-20T16:45:00Z", "unchecked",
    "Three shallow, evenly spaced dips in a star's light. A planet crossing the star is one explanation; a background eclipsing binary is another. Needs follow-up."),
  make(7, "active_galaxy", 0.64, "rubin", 150.4, 2.2, "2026-09-19T09:03:12Z", "known",
    "The centre of a known galaxy flickered by a few percent over two weeks, as actively feeding black holes do."),
  make(8, "unknown", 0.21, "rubin", 12.9, -44.3, "2026-09-25T01:27:33Z", "unchecked",
    "Something changed in the difference image, but the shape doesn't match any type well. It could be an image artefact."),
];

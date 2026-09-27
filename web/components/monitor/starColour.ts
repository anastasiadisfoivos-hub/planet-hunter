// A star's colour from its temperature (DESIGN.md: Colour, "star colour"). Blackbody sRGB for a D65 white,
// Mitchell Charity's table (vendian.org/mncharity/dir3/blackbody), sampled every 200 K from 2000 to 12000 K,
// with one stated boost: chroma x1.6 around Rec. 709 luma, so the pale true colours read on paper.
// No React and no "@/" value imports, so node --test can load it directly.

const T_MIN = 2000;
const T_STEP = 200;
const HEX = "ff8912ff932cff9d3fffa54fffad5effb46bffbb78ffc184ffc78fffcc99ffd1a3ffd5adffd9b6ffddbeffe1c6ffe4ceffe8d5ffebdcffeee3fff0e9fff3effff5f5fff8fbfef9fff9f6fff5f3fff0f1ffedefffe9edffe6ebffe3e9ffe0e7ffdde6ffdae4ffd8e3ffd6e1ffd3e0ffd1dfffcfddffcedcffccdbffcadaffc9d9ffc7d8ffc6d8ffc4d7ffc3d6ffc2d5ffc1d4ffc0d4ffbfd3ff";
const N = HEX.length / 6;
export const T_MAX = T_MIN + (N - 1) * T_STEP;
export const SATURATION = 1.6;

type Rgb = [number, number, number];
const TABLE: Rgb[] = Array.from({ length: N }, (_, i) => [0, 2, 4].map((o) => parseInt(HEX.slice(i * 6 + o, i * 6 + o + 2), 16) / 255) as Rgb);

function blackbody(teff: number): Rgb {
  const x = (Math.min(T_MAX, Math.max(T_MIN, teff)) - T_MIN) / T_STEP;
  const i = Math.min(N - 2, Math.floor(x));
  const f = x - i;
  const a = TABLE[i];
  const b = TABLE[i + 1];
  return [0, 1, 2].map((k) => a[k] + (b[k] - a[k]) * f) as Rgb;
}

/** The star's colour as a CSS hex, or null when the catalogue has no temperature. */
export function starHex(teff: number | null | undefined): string | null {
  if (teff == null || !(teff > 0)) return null;
  const c = blackbody(teff);
  const y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  const s = c.map((v) => Math.max(0, y + (v - y) * SATURATION));
  const m = Math.max(...s);
  return "#" + s.map((v) => Math.round((v / m) * 255).toString(16).padStart(2, "0")).join("");
}

/** Stops for the key: the scale from cool to hot, as a CSS gradient. */
export const SCALE_TEMPS = [2500, 3500, 4500, 5500, 6500, 8000, 10000];
export function scaleGradient(): string {
  return `linear-gradient(90deg, ${SCALE_TEMPS.map((t, i) => `${starHex(t)} ${Math.round((i / (SCALE_TEMPS.length - 1)) * 100)}%`).join(", ")})`;
}

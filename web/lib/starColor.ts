// Star colour from effective temperature: Mitchell Charity's blackbody table (sRGB, D65 white),
// plus one display saturation boost so colours read on a black sky. See CREDITS.md.

import { BB_HEX, BB_T_MIN, BB_T_STEP } from "./starColorTable.ts";

export type Rgb = [number, number, number];

const N = BB_HEX.length / 6;
const T_MAX = BB_T_MIN + (N - 1) * BB_T_STEP;
const TABLE: Rgb[] = Array.from({ length: N }, (_, i) => [0, 2, 4].map((o) => parseInt(BB_HEX.slice(i * 6 + o, i * 6 + o + 2), 16) / 255) as Rgb);

/**
 * The one documented display boost: chroma is scaled by this factor around Rec. 709 luma, then the
 * colour is renormalised so its brightest channel is 1. True blackbody colours are pale (a 3000 K red
 * dwarf is peach, a 20000 K star barely blue); on pure black they read as white without it.
 */
export const DISPLAY_SATURATION = 1.75;

/** Blackbody sRGB (0..1, peak channel 1) for a temperature in kelvin, clamped to 1000..40000 K. */
export function teffToSrgb(teff: number): Rgb {
  const x = (Math.min(T_MAX, Math.max(BB_T_MIN, teff)) - BB_T_MIN) / BB_T_STEP;
  const i = Math.min(N - 2, Math.floor(x));
  const f = x - i;
  const a = TABLE[i];
  const b = TABLE[i + 1];
  return [a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f, a[2] + (b[2] - a[2]) * f];
}

/** Effective temperature from B-V (Ballesteros 2012, EPL 97, 34008). */
export function bvToTeff(bv: number): number {
  return 4600 * (1 / (0.92 * bv + 1.7) + 1 / (0.92 * bv + 0.62));
}

/** Display colour (sRGB 0..1) for a star. Missing temperature: neutral white, no boost. */
export function starColor(teff: number): Rgb {
  if (!(teff > 0)) return [1, 1, 1];
  const c = teffToSrgb(teff);
  const y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  const s = c.map((v) => Math.max(0, y + (v - y) * DISPLAY_SATURATION));
  const m = Math.max(...s);
  return [s[0] / m, s[1] / m, s[2] / m];
}

/** sRGB channel to linear, for shaders (the bloom composer encodes back to sRGB on output). */
export function srgbToLinear(v: number): number {
  return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
}

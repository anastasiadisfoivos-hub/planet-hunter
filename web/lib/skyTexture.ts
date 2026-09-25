// Bakes the sky's data layers into one equirectangular RGBA texture for the sky shader:
//   R = Rubin coverage (blurred, so the shader can draw a smooth outline at the 0.5 contour)
//   G = Rubin alerts heatmap (log-scaled)
// u = RA / 360, v = (Dec + 90) / 180.
//
// All HEALPix lookups happen here, once, when the data loads: never during a React render.

import { ang2pix_nest, ang2pix_ring } from "@hscmap/healpix";
import { DEG } from "./sky.ts";

export const TEX_W = 1024;
export const TEX_H = 512;

export type HealpixOrder = "nest" | "ring";

/**
 * HEALPix pixel index for every texel, per (nside, ordering), computed once. @hscmap/healpix calls
 * console.assert twice per lookup; in Next dev the console is instrumented and 500k calls froze the
 * tab until it ran out of memory. So the asserts are muted for this one loop, and the table is reused.
 */
const cache = new Map<string, Int32Array>();
export function texelPixels(nside: number, order: HealpixOrder): Int32Array {
  const key = `${order}:${nside}`;
  const hit = cache.get(key);
  if (hit) return hit;
  const out = new Int32Array(TEX_W * TEX_H);
  const f = order === "ring" ? ang2pix_ring : ang2pix_nest;
  const assert = console.assert;
  console.assert = () => {};
  try {
    for (let y = 0; y < TEX_H; y++) {
      const theta = (90 - (((y + 0.5) / TEX_H) * 180 - 90)) * DEG;
      for (let x = 0; x < TEX_W; x++) out[y * TEX_W + x] = f(nside, theta, ((x + 0.5) / TEX_W) * 360 * DEG);
    }
  } finally {
    console.assert = assert;
  }
  cache.set(key, out);
  return out;
}

/** Box blur, `passes` times, wrapping in RA and clamping at the poles. Three passes approximate a gaussian. */
function blur(src: Float32Array, radius: number, passes: number): Float32Array {
  const a = Float32Array.from(src);
  const t = new Float32Array(a.length);
  const n = 2 * radius + 1;
  for (let p = 0; p < passes; p++) {
    for (let y = 0; y < TEX_H; y++) {
      const row = y * TEX_W;
      for (let x = 0; x < TEX_W; x++) {
        let s = 0;
        for (let k = -radius; k <= radius; k++) s += a[row + ((x + k + TEX_W) % TEX_W)];
        t[row + x] = s / n;
      }
    }
    for (let y = 0; y < TEX_H; y++) {
      for (let x = 0; x < TEX_W; x++) {
        let s = 0;
        for (let k = -radius; k <= radius; k++) s += t[Math.min(TEX_H - 1, Math.max(0, y + k)) * TEX_W + x];
        a[y * TEX_W + x] = s / n;
      }
    }
  }
  return a;
}

/**
 * Coverage field: 1 inside the footprint, 0 outside, blurred over about one footprint pixel
 * (nside 64 is 0.9 degree) so the 0.5 contour is a smooth curve instead of a HEALPix staircase.
 */
export function bakeFootprintField(nside: number, codes: Uint8Array): Float32Array {
  const pix = texelPixels(nside, "nest");
  const f = new Float32Array(pix.length);
  for (let i = 0; i < pix.length; i++) f[i] = codes[pix[i]] > 0 ? 1 : 0;
  return blur(f, 2, 3);
}

/** Parse "healpix nside=N" from the heatmap's grid field. */
export function heatmapNside(grid: string): number {
  const m = /nside\s*=\s*(\d+)/.exec(grid);
  if (!m) throw new Error(`Unrecognised heatmap grid "${grid}"`);
  return Number(m[1]);
}

export type HeatmapFile = {
  generated_at: string;
  grid: string;
  window?: { start: string; end: string };
  cells: { pix: number; counts: Record<string, number> }[];
};

/** Heatmap field, log-scaled 0..1. sources/ bins with HEALPix RING ordering (skysources.heatmap). */
export function bakeHeatmapField(hm: HeatmapFile): { field: Float32Array; max: number; total: number } {
  const nside = heatmapNside(hm.grid);
  const values = new Float32Array(12 * nside * nside);
  let max = 0;
  let total = 0;
  for (const c of hm.cells) {
    let n = 0;
    for (const v of Object.values(c.counts)) n += v ?? 0;
    values[c.pix] = n;
    total += n;
    if (n > max) max = n;
  }
  const pix = texelPixels(nside, "ring");
  const norm = max > 0 ? 1 / Math.log1p(max) : 0;
  const field = new Float32Array(pix.length);
  for (let i = 0; i < pix.length; i++) field[i] = Math.log1p(values[pix[i]]) * norm;
  return { field, max, total };
}

/** Pack the fields into RGBA bytes. */
export function packSkyTexture(coverage: Float32Array, heat: Float32Array): Uint8Array {
  const buf = new Uint8Array(TEX_W * TEX_H * 4);
  for (let i = 0; i < coverage.length; i++) {
    buf[i * 4] = Math.round(coverage[i] * 255);
    buf[i * 4 + 1] = Math.round(heat[i] * 255);
    buf[i * 4 + 3] = 255;
  }
  return buf;
}

/** Texel index for (ra, dec) in degrees. */
export function texelAt(raDeg: number, decDeg: number): number {
  const x = Math.min(TEX_W - 1, Math.floor((((raDeg % 360) + 360) % 360) / 360 * TEX_W));
  const y = Math.min(TEX_H - 1, Math.max(0, Math.floor(((decDeg + 90) / 180) * TEX_H)));
  return y * TEX_W + x;
}

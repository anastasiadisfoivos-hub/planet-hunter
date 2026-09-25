// Bakes the sky layers into one equirectangular RGBA texture, sampled by the sky shader:
//   R = Rubin footprint, G = heatmap (log-scaled, current type filter), B = Rubin tonight tiles.
// u = RA / 360, v = (Dec + 90) / 180.

import { ang2pix_nest } from "@hscmap/healpix";
import type { CatchType, Heatmap } from "@/lib/contract";
import { heatmapNside, type Footprint, type RubinTonight } from "./data";
import { DEG, radecToVec } from "./sky";

export const TEX_W = 512;
export const TEX_H = 256;

type Texel = { theta: number; phi: number; ra: number; dec: number };

let texelCache: Texel[] | null = null;
function texels(): Texel[] {
  if (texelCache) return texelCache;
  const out: Texel[] = new Array(TEX_W * TEX_H);
  for (let y = 0; y < TEX_H; y++) {
    const dec = ((y + 0.5) / TEX_H) * 180 - 90;
    for (let x = 0; x < TEX_W; x++) {
      const ra = ((x + 0.5) / TEX_W) * 360;
      out[y * TEX_W + x] = { theta: (90 - dec) * DEG, phi: ra * DEG, ra, dec };
    }
  }
  return (texelCache = out);
}

export function bakeFootprint(buf: Uint8Array, fp: Footprint) {
  const t = texels();
  for (let i = 0; i < t.length; i++) {
    buf[i * 4] = fp.codes[ang2pix_nest(fp.nside, t[i].theta, t[i].phi)] > 0 ? 255 : 0;
    buf[i * 4 + 3] = 255;
  }
}

/** Returns the largest count found, for the legend. */
export function bakeHeatmap(buf: Uint8Array, hm: Heatmap, type: CatchType | "all"): number {
  // The contract says "healpix nside=N" without an ordering; we assume NESTED (see report).
  const nside = heatmapNside(hm.grid);
  const values = new Float32Array(12 * nside * nside);
  let max = 0;
  for (const c of hm.cells) {
    let n = 0;
    if (type === "all") for (const v of Object.values(c.counts)) n += v ?? 0;
    else n = c.counts[type] ?? 0;
    values[c.pix] = n;
    if (n > max) max = n;
  }
  const t = texels();
  const norm = max > 0 ? 1 / Math.log1p(max) : 0;
  for (let i = 0; i < t.length; i++) {
    const n = values[ang2pix_nest(nside, t[i].theta, t[i].phi)];
    buf[i * 4 + 1] = Math.round(Math.log1p(n) * norm * 255);
  }
  return max;
}

export function bakeTonight(buf: Uint8Array, tonight: RubinTonight) {
  const t = texels();
  const cosR = Math.cos(tonight.field_radius_deg * DEG);
  const centers = tonight.tiles.map((p) => radecToVec(p.ra_deg, p.dec_deg));
  for (let i = 0; i < t.length; i++) {
    const v = radecToVec(t[i].ra, t[i].dec);
    let hit = 0;
    for (const c of centers) {
      const d = v[0] * c[0] + v[1] * c[1] + v[2] * c[2];
      if (d > cosR) {
        // 255 inside; the shader draws the rim from the gradient of this channel.
        hit = 255;
        break;
      }
    }
    buf[i * 4 + 2] = hit;
  }
}

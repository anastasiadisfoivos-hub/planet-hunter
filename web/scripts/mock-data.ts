// DEMO DATA generator: web/public/mock/heatmap.json (contract shape) and
// web/public/mock/rubin-tonight.json (web-only shape, not in the contract).
//
//   node web/scripts/mock-data.ts
//
// Seeded, so re-running gives the same files. Nothing here is real survey output.

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";
import healpix from "@hscmap/healpix";
import { CATCH_TYPES, type CatchType, type Heatmap } from "../lib/contract.ts";
import { DEG, huntingGround } from "../lib/sky.ts";

const here = path.dirname(fileURLToPath(import.meta.url));
const mockDir = path.join(here, "..", "public", "mock");
const dataDir = path.join(here, "..", "public", "data");

let seed = 20260925;
function rand() {
  seed = (seed + 0x6d2b79f5) >>> 0;
  let t = seed;
  t = Math.imul(t ^ (t >>> 15), t | 1);
  t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
  return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
}

/** Poisson draw (Knuth; fine for the small means used here). */
function poisson(mean: number): number {
  if (mean > 30) return Math.max(0, Math.round(mean + Math.sqrt(mean) * (rand() * 2 - 1)));
  const L = Math.exp(-mean);
  let k = 0;
  let p = 1;
  do {
    k++;
    p *= rand();
  } while (p > L);
  return k - 1;
}

const WEEKLY: Record<string, Partial<Record<CatchType, number>>> = {
  solar: { asteroid: 40, near_earth_object: 0.6, trans_neptunian_object: 0.3, comet: 0.08, variable_star: 3, unknown: 0.4 },
  bulge: { microlensing: 2, variable_star: 30, flare: 6, eclipsing_binary: 8, unknown: 1 },
  deep: { supernova: 1.2, active_galaxy: 3, tidal_disruption_event: 0.05, kilonova: 0.003, variable_star: 2, unknown: 0.3 },
  none: { variable_star: 5, flare: 0.8, supernova: 0.4, active_galaxy: 0.5, unknown: 0.3 },
};

async function main() {
  const fp = JSON.parse(await readFile(path.join(dataDir, "rubin-footprint.json"), "utf8"));
  const codes = new Uint8Array(12 * fp.nside * fp.nside);
  for (let k = 0, i = 0; k < fp.rle.length; k += 2) {
    codes.fill(fp.rle[k], i, i + fp.rle[k + 1]);
    i += fp.rle[k + 1];
  }

  // Heatmap on nside=16 (NESTED ordering, like the footprint file).
  const NSIDE = 16;
  const cells: Heatmap["cells"] = [];
  for (let pix = 0; pix < 12 * NSIDE * NSIDE; pix++) {
    const { theta, phi } = healpix.pix2ang_nest(NSIDE, pix);
    const dec = 90 - theta / DEG;
    const ra = phi / DEG;
    const inside = codes[healpix.ang2pix_nest(fp.nside, theta, phi)] > 0;
    const rates = WEEKLY[huntingGround(ra, dec) ?? "none"];
    const counts: Partial<Record<CatchType, number>> = {};
    for (const t of CATCH_TYPES) {
      let mean = rates[t] ?? 0;
      // TESS watches the whole sky: its types show up outside Rubin's footprint too.
      const tess = t === "planet_candidate" || t === "eclipsing_binary" || t === "flare";
      if (t === "planet_candidate") mean = 0.15;
      if (!inside && !tess) mean = 0;
      const n = poisson(mean * (0.5 + rand()));
      if (n > 0) counts[t] = n;
    }
    if (Object.keys(counts).length) cells.push({ pix, counts });
  }
  const heatmap: Heatmap = {
    generated_at: "2026-09-21T10:00:00Z",
    grid: `healpix nside=${NSIDE}`,
    cells,
  };

  // Rubin tonight: ~40 pointings inside the footprint, paired visits ~33 min apart.
  const tiles: { ra_deg: number; dec_deg: number; band: string; time: string }[] = [];
  const bands = ["g", "r", "i", "z"];
  let t = Date.parse("2026-09-25T23:40:00Z");
  while (tiles.length < 40) {
    const ra = 300 + rand() * 120; // a plausible slab of sky that is up in late September
    const dec = -75 + rand() * 80;
    const r = ((ra % 360) + 360) % 360;
    if (codes[healpix.ang2pix_nest(fp.nside, (90 - dec) * DEG, r * DEG)] === 0) continue;
    const band = bands[Math.floor(rand() * bands.length)];
    tiles.push({ ra_deg: Number(r.toFixed(3)), dec_deg: Number(dec.toFixed(3)), band, time: new Date(t).toISOString() });
    tiles.push({ ra_deg: Number(r.toFixed(3)), dec_deg: Number(dec.toFixed(3)), band, time: new Date(t + 33 * 60000).toISOString() });
    t += 9 * 60000;
  }
  const tonight = {
    generated_at: "2026-09-25T18:00:00Z",
    night: "2026-09-25",
    field_radius_deg: 1.75,
    tiles,
  };

  for (const [name, obj] of [
    ["heatmap.json", heatmap],
    ["rubin-tonight.json", tonight],
  ] as const) {
    const json = JSON.stringify(obj);
    await writeFile(path.join(mockDir, name), json);
    console.log(`${name}: ${json.length} B raw, ${gzipSync(json).length} B gzip`);
  }
  console.log(`heatmap cells: ${cells.length}, tonight tiles: ${tiles.length}`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

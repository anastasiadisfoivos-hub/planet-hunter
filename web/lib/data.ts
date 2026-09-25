// Loaders and lookups for the static map data in /public/data and /public/mock.

import { ang2pix_nest } from "@hscmap/healpix";
import type { Heatmap } from "@/lib/contract";
import { DEG, galactic } from "./sky";

export type FootprintFile = {
  source: string;
  source_url: string;
  reference: string;
  source_version: string;
  generated_at: string;
  nside: number;
  order: "nested";
  labels: string[];
  rle: number[];
};

export type Footprint = FootprintFile & { codes: Uint8Array };

export type HostsFile = {
  source: string;
  distance_note: string;
  generated_at: string;
  count: number;
  dist_refs: string[];
  name: string[];
  tic: number[];
  gaia: string[];
  ra: number[];
  dec: number[];
  dist: number[];
  npl: number[];
  teff: number[];
  /** Stellar radius in solar radii; 0 when not listed. */
  rad: number[];
  /** V magnitude from Earth; 99 when not listed. */
  vmag: number[];
  ref: number[];
};

/** Rubin tonight tiles. Not part of the shared contract: a web-only demo shape. */
export type RubinTonight = {
  generated_at: string;
  night: string;
  field_radius_deg: number;
  tiles: { ra_deg: number; dec_deg: number; band: string; time: string }[];
};

export type SkyObjectsFile = {
  generated_at: string;
  note: string;
  sources: { nebulae: string; stars: string };
  nebulae: [number, number, number, number, number][];
  stars: { ra: number[]; dec: number[]; mag: number[]; bv: number[] };
};

export type MapData = {
  footprint: Footprint;
  hosts: HostsFile;
  heatmap: Heatmap;
  tonight: RubinTonight;
  sky: SkyObjectsFile;
};

export function decodeFootprint(fp: FootprintFile): Footprint {
  const codes = new Uint8Array(12 * fp.nside * fp.nside);
  let i = 0;
  for (let k = 0; k < fp.rle.length; k += 2) {
    codes.fill(fp.rle[k], i, i + fp.rle[k + 1]);
    i += fp.rle[k + 1];
  }
  return { ...fp, codes };
}

export function footprintLabel(fp: Footprint, raDeg: number, decDeg: number): string {
  const pix = ang2pix_nest(fp.nside, (90 - decDeg) * DEG, raDeg * DEG);
  return fp.labels[fp.codes[pix]];
}

export function inFootprint(fp: Footprint, raDeg: number, decDeg: number): boolean {
  return footprintLabel(fp, raDeg, decDeg) !== "outside";
}

/** Plain-language reason a sky trap can't go at this position (only called when outside). */
export function outsideReason(raDeg: number, decDeg: number): string {
  if (decDeg > 30) {
    return "Rubin sits in Chile, 30° south of the equator. This part of the sky never climbs high enough there for the survey to watch it.";
  }
  const { b } = galactic(raDeg, decDeg);
  if (Math.abs(b) < 20) {
    return "Thick dust in the Milky Way's disc dims this patch, so the survey spends its time elsewhere.";
  }
  return "This patch is outside the area Rubin's survey plans to cover, so it won't be watched often enough to catch anything.";
}

/** Parse "healpix nside=N" from the contract's heatmap.grid. */
export function heatmapNside(grid: string): number {
  const m = /nside\s*=\s*(\d+)/.exec(grid);
  if (!m) throw new Error(`Unrecognised heatmap grid "${grid}"`);
  return Number(m[1]);
}

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function loadMapData(): Promise<MapData> {
  const [fp, hosts, heatmap, tonight, sky] = await Promise.all([
    getJson<FootprintFile>("/data/rubin-footprint.json"),
    getJson<HostsFile>("/data/hosts.json"),
    getJson<Heatmap>("/mock/heatmap.json"),
    getJson<RubinTonight>("/mock/rubin-tonight.json"),
    getJson<SkyObjectsFile>("/data/sky-objects.json"),
  ]);
  return { footprint: decodeFootprint(fp), hosts, heatmap, tonight, sky };
}

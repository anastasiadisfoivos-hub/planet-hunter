// Loaders and lookups for the static map data in /public/data and /public/mock.

import { bakeFootprintField, bakeHeatmapField, packSkyTexture, type HeatmapFile } from "./skyTexture";

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
  heatmap: HeatmapFile & { max: number; total: number };
  sky: SkyObjectsFile;
  /** Baked equirectangular RGBA for the sky shader (see lib/skyTexture.ts). */
  skyTexture: Uint8Array;
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

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${url}: ${res.status}`);
  return res.json() as Promise<T>;
}

export async function loadMapData(): Promise<MapData> {
  const [fp, hosts, heatmap, sky] = await Promise.all([
    getJson<FootprintFile>("/data/rubin-footprint.json"),
    getJson<HostsFile>("/data/hosts.json"),
    getJson<HeatmapFile>("/data/heatmap.rubin-sample.json"),
    getJson<SkyObjectsFile>("/data/sky-objects.json"),
  ]);
  const footprint = decodeFootprint(fp);
  // Every HEALPix lookup happens here, once, before anything renders.
  const coverage = bakeFootprintField(footprint.nside, footprint.codes);
  const heat = bakeHeatmapField(heatmap);
  return {
    footprint,
    hosts,
    heatmap: { ...heatmap, max: heat.max, total: heat.total },
    sky,
    skyTexture: packSkyTexture(coverage, heat.field),
  };
}

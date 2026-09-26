// The map's stars, flattened for the Lab: planet hosts (hosts.json) and bright catalogue stars
// (sky-objects.json + bright-stars.json), each with a temperature and a visible-light brightness.

import type { BrightStarsFile, HostsFile, SkyObjectsFile } from "@/lib/data";
import { bvToTeff } from "@/lib/starColor";

export type LabStar = {
  name: string;
  kind: "host" | "bright";
  /** Index in hosts.json or in sky-objects stars. */
  i: number;
  teff: number;
  /** Temperature estimated from B−V rather than catalogued. */
  teffEstimated: boolean;
  /** Visible-light luminosity in Suns, from V magnitude and distance (no bolometric correction). */
  lum: number;
  /** Where the sky deep link points: /sky?host=<tic> or /sky?bright=<index>. */
  href: string;
  planets: string[];
  /** TIC number when the star is a planet host (its own lab is /lab/star/<tic>). */
  tic: number | null;
};

/** Absolute visual magnitude of the Sun. */
const SUN_MV = 4.83;

export function visualLum(vmag: number, pc: number): number {
  const mv = vmag - 5 * Math.log10(pc / 10);
  return 10 ** (-0.4 * (mv - SUN_MV));
}

export async function loadLabStars(signal?: AbortSignal): Promise<LabStar[]> {
  const get = <T>(u: string) =>
    fetch(u, { signal }).then((r) => {
      if (!r.ok) throw new Error(`${u}: ${r.status}`);
      return r.json() as Promise<T>;
    });
  const [hosts, sky, bright] = await Promise.all([
    get<HostsFile>("/data/hosts.json"),
    get<SkyObjectsFile>("/data/sky-objects.json"),
    get<BrightStarsFile>("/data/bright-stars.json"),
  ]);
  const out: LabStar[] = [];
  const seenHost = new Set<number>();
  const st = sky.stars;
  for (let i = 0; i < st.ra.length; i++) {
    const pc = bright.dist[i];
    if (!(pc > 0) || !Number.isFinite(st.bv[i])) continue;
    const teff = Math.round(bvToTeff(st.bv[i]) / 10) * 10;
    const host = bright.host[i];
    if (host >= 0) seenHost.add(host);
    out.push({
      name: bright.name[i] || `HIP ${bright.hip[i]}`,
      kind: "bright",
      i,
      teff,
      teffEstimated: true,
      lum: visualLum(st.mag[i], pc),
      href: `/sky?bright=${i}`,
      planets: host >= 0 ? (hosts.planets?.[host] ?? []) : [],
      tic: host >= 0 ? hosts.tic[host] : null,
    });
  }
  for (let i = 0; i < hosts.name.length; i++) {
    if (seenHost.has(i) || !(hosts.teff[i] > 0) || !(hosts.dist[i] > 0) || !(hosts.vmag?.[i] < 99)) continue;
    out.push({
      name: hosts.name[i],
      kind: "host",
      i,
      teff: hosts.teff[i],
      teffEstimated: false,
      lum: visualLum(hosts.vmag[i], hosts.dist[i]),
      href: `/sky?host=${hosts.tic[i]}`,
      planets: hosts.planets?.[i] ?? [],
      tic: hosts.tic[i],
    });
  }
  return out;
}

/** Well-known stars offered as quick picks, when present in the data. */
export const FAMOUS = ["Betelgeuse", "Antares", "Aldebaran", "Arcturus", "Capella", "Procyon", "Sirius", "Vega", "Regulus", "Rigel", "Spica", "Proxima Cen", "WASP-18", "WASP-121"];

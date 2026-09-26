// Short names and dates for event tiles (DESIGN.md, Words: a tile is a name of ≤ 4 words plus its caption line).

import type { SkyEvent } from "../../lib/contract.ts";

const PREFIXES = [
  "Supernova candidate ",
  "Variable star candidate ",
  "Possible near-Earth object ",
  "Possible comet ",
  "Gamma-ray burst ",
  "Transient candidate ",
  "Active galaxy flare candidate ",
];

/** "Supernova candidate ZTF26abeqbvy" → "ZTF26abeqbvy"; "Coronal mass ejection (805 km/s)" → "CME 805 km/s". The type is the glyph. */
export function shortName(e: SkyEvent): string {
  let t = e.title;
  const cme = /^Coronal mass ejection \((.+)\)$/.exec(t);
  if (cme) return `CME ${cme[1]}`;
  for (const p of PREFIXES) if (t.startsWith(p)) t = t.slice(p.length);
  return t.replace(/ \((known asteroid|blazar in high state|TNS nova|TNS TDE)\)$/, "");
}

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function dayLabel(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}

/** Group label for a UTC day relative to "now": Today, Yesterday, or "23 Sep". */
export function dayGroup(iso: string, now: number): string {
  const day = (t: number) => Math.floor(t / 86400000);
  const diff = day(now) - day(Date.parse(iso));
  return diff === 0 ? "Today" : diff === 1 ? "Yesterday" : dayLabel(iso);
}

/** "25 Sep 2026, 11:49 UTC" */
export function longUtc(iso: string): string {
  const d = new Date(iso);
  return `${d.getUTCDate()} ${MON[d.getUTCMonth()]} ${d.getUTCFullYear()}, ${iso.slice(11, 16)} UTC`;
}

export const eventHref = (id: string) => `/events/${encodeURIComponent(id)}`;

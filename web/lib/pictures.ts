// Every picture on the site is a real photograph or real instrument data, stored in public/images/ and credited in
// public/images/credits.json (DESIGN.md, Pictures). This module is the only way pages look them up.

import creditsJson from "../public/images/credits.json";
import type { SkyEvent } from "./contract.ts";
import { pictureKey } from "./pictureKeys.ts";

export type Credit = {
  url: string;
  title: string;
  credit: string;
  licence: string;
  source: string;
  width: number;
  height: number;
  file?: string;
  archive?: boolean;
  event?: string;
  note?: string;
  kind?: string;
  /** Where the event (or target star) sits in the frame, as fractions: the crosshair. */
  mark?: { u: number; v: number };
};

export type Pic = Credit & { key: string; src: string };

export const CREDITS = creditsJson as Record<string, Credit>;

export function pic(key: string): Pic | null {
  const c = CREDITS[key];
  return c ? { ...c, key, src: `/images/${key}` } : null;
}

export const eventPic = (id: string) => pic(`events/${pictureKey(id)}.jpg`);
export const wherePic = (id: string) => pic(`sky/where/${pictureKey(id)}.jpg`);
export const starPic = (tic: number) => pic(`stars/tic${tic}.jpg`);

/** A short name for where a picture comes from, for the caption line. */
export function sourceName(c: Credit): string {
  const s = c.credit;
  const rules: [RegExp, string][] = [
    [/DESI Legacy/i, "DESI Legacy Surveys"],
    [/Pan-STARRS|PS1/i, "Pan-STARRS1"],
    [/SkyMapper/i, "SkyMapper"],
    [/Digitized Sky/i, "DSS2"],
    [/SDO|AIA/i, "NASA SDO"],
    [/Rubin/i, "Rubin Observatory"],
    [/^ESO\//i, s.replace(/\s*\(.*\)$/, "")],
    [/TESS/i, "NASA TESS"],
    [/Webb|CSA/i, "NASA, ESA, CSA, STScI"],
    [/ESA|STScI|Hubble/i, "NASA, ESA"],
    [/JPL/i, "NASA/JPL"],
    [/ZTF|ALeRCE/i, "ZTF"],
  ];
  for (const [re, name] of rules) if (re.test(s)) return name;
  return s.split(",")[0].slice(0, 28);
}

/** The flag an event's caption line carries: archive, a machine guess with its confidence, or the time. */
export function eventFlag(e: SkyEvent, p: Pic | null): string {
  if (p?.archive) return "Archive";
  if (e.confidence_basis === "machine_guess") return `Guess ${Math.round(e.confidence * 100)}%`;
  if (e.type === "near_earth_object" || e.type === "comet" || e.type === "asteroid") return "";
  return `${e.observed_at.slice(11, 16)} UTC`;
}

/** One honesty sentence for the i, when the picture needs one. */
export function honesty(e: SkyEvent | null, p: Pic): string | null {
  if (p.archive && e) return "An archive picture taken years before the event. The event itself is not in it; the crosshair marks where it happened.";
  if (p.archive) return "An archive survey picture. The crosshair marks the star.";
  if (p.kind === "solar" || /SDO/.test(p.credit)) return "The whole Sun near the reported time.";
  return null;
}

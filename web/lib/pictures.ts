// Every picture on the site is a real photograph or real instrument data, stored in public/images/ and credited in
// public/images/credits.json (DESIGN.md, Pictures). This module is the only way pages look them up.

import creditsJson from "../public/images/credits.json";

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

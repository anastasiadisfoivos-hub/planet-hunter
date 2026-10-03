// Reading VET's vetting block, in either shape (lib/api.ts `Vetting`). No React, so node --test can load it.

import type { Vetting } from "../../lib/api.ts";

/** The neighbours Gaia says are bright enough to cause the dip, and the radius searched (arcseconds). */
export function mimics(g: Vetting["gaia"]): { count: number; radius: number } {
  const listed = g.neighbours.filter((n) => n.could_mimic ?? n.can_mimic).length;
  return { count: g.n_could_mimic ?? listed, radius: g.radius_arcsec ?? 42 };
}

/** Whether Gaia DR3 calls the star variable: skyvet's object, or the mock's yes/no. */
export function gaiaVariable(v: Vetting["variability"]["gaia_variable"]): boolean {
  if (v == null) return false;
  if (typeof v === "boolean") return v;
  return v.phot_variable_flag === "VARIABLE";
}

/** Whether a part ran. The mock's gaia and variability blocks have no `ran`: they did. */
export const ran = (part: { ran?: boolean }): boolean => part.ran ?? true;

/** A part that did not run: why, when it says. */
export const notRun = (part: { reason?: string }): string => (part.reason ? `not run: ${part.reason}` : "not run yet");

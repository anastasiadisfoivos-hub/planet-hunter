import type { StarLab } from "@/lib/api";
import { massFromTeff } from "../transit";

export type StarMass = { value: number; estimated: boolean };

/** The star's mass in Suns: catalogued when listed, else estimated from its temperature. */
export function starMass(lab: StarLab): StarMass | null {
  if (lab.mass && lab.mass > 0) return { value: lab.mass, estimated: false };
  if (lab.teff) return { value: Math.round(massFromTeff(lab.teff) * 100) / 100, estimated: true };
  return null;
}

/** Why there is no light curve, in words. */
export function lightcurveReason(lab: StarLab): string {
  switch (lab.lightcurve.reason_if_not) {
    case "not_analyzed":
      return "Not analyzed yet. Its TESS light curve hasn't been downloaded and searched.";
    case "no_tess_data":
      return "No TESS data. TESS hasn't recorded a light curve of this star that the analysis can use.";
    case "too_bright":
      return `Too bright for TESS's camera.${lab.tmag != null ? ` At TESS magnitude ${lab.tmag.toFixed(2)} it` : " It"} floods the detector's pixels, so its brightness can't be measured cleanly enough to see a transit.`;
    default:
      return lab.lightcurve.reason_if_not ? `No light curve: ${lab.lightcurve.reason_if_not}.` : "No light curve for this star.";
  }
}

export function LockedLightcurve({ lab }: { lab: StarLab }) {
  return <>{lightcurveReason(lab)}</>;
}

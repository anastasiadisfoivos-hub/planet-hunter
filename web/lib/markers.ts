// Where each event goes on the sky. Sky-frame events at their RA/Dec. Sun-frame events around the
// Sun's current position (they happened on the Sun, which is 0.5 degree wide: several markers would
// otherwise sit on one point, so they fan out on a 1.2 degree circle, newest at the top). Earth-frame
// events (fireballs, storms) are not in the sky and have no marker.

import { CATEGORY_OF, type Category, type SkyEvent } from "./contract.ts";
import { recency } from "./events.ts";
import { sunRaDec } from "./sun.ts";

export type Marker = {
  id: string;
  title: string;
  ra: number;
  dec: number;
  category: Category;
  recency: number;
  /** Observed in the last 24 hours: the marker pulses (unless motion is reduced). */
  fresh: boolean;
  onSun: boolean;
};

const DAY = 24 * 3600_000;

export const SUN_FAN_DEG = 1.2;

export function buildMarkers(events: SkyEvent[], now: number): { markers: Marker[]; sun: { ra: number; dec: number } } {
  const sun = sunRaDec(now);
  const onSun = events.filter((e) => e.location.frame === "sun").sort((a, b) => b.observed_at.localeCompare(a.observed_at));
  const markers: Marker[] = [];
  for (const e of events) {
    const age = now - Date.parse(e.observed_at);
    const base = { id: e.id, title: e.title, category: CATEGORY_OF[e.type], recency: recency(e.observed_at, now), fresh: age >= 0 && age < DAY };
    if (e.location.frame === "sky") {
      markers.push({ ...base, ra: e.location.ra_deg, dec: e.location.dec_deg, onSun: false });
    } else if (e.location.frame === "sun") {
      const k = onSun.indexOf(e);
      const n = onSun.length;
      // One event sits on the Sun; more fan out around it, starting straight up (north).
      const a = n === 1 ? 0 : (k / n) * 2 * Math.PI;
      const r = n === 1 ? 0 : SUN_FAN_DEG;
      const dec = sun.dec + r * Math.cos(a);
      const ra = sun.ra + (r * Math.sin(a)) / Math.max(0.2, Math.cos((sun.dec * Math.PI) / 180));
      markers.push({ ...base, ra: (ra + 360) % 360, dec, onSun: true });
    }
  }
  return { markers, sun };
}

/** Field of view that frames an event on the sky: its error circle with room around it, 10 to 50 degrees (a point source keeps its neighbouring stars in view). */
export function eventFov(e: SkyEvent): number {
  return e.location.frame === "sky" ? Math.max(10, Math.min(50, e.location.error_deg * 5)) : 8;
}

/** Where "Show on map" points: the event's position, or the Sun's position now for Sun events. */
export function eventTarget(e: SkyEvent, now: number): { ra: number; dec: number } | null {
  if (e.location.frame === "sky") return { ra: e.location.ra_deg, dec: e.location.dec_deg };
  if (e.location.frame === "sun") return sunRaDec(now);
  return null;
}

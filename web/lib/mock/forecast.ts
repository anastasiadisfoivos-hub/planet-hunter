// DEMO DATA. A stand-in for the forecast/ service until api/ exists.
// Returns an object shaped exactly like the shared contract's Forecast, seeded from the sphere so
// the same patch always gives the same numbers. Nothing here is a real prediction.

import type { CatchType, Forecast, Sphere } from "@/lib/contract";
import { capAreaDeg2, eclipticLatitude, huntingGround, type HuntingGround } from "@/lib/sky";

export type ForecastWindow = "tonight" | "week";

/** mulberry32: tiny deterministic PRNG. */
function rng(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function seedOf(s: Sphere): number {
  // Quantise so tiny pointer jitter doesn't reshuffle the numbers while dragging.
  const q = Math.round(s.ra_deg * 4) * 7919 + Math.round((s.dec_deg + 90) * 4) * 104729;
  return q ^ 0x5bd1e995;
}

// Rough per-square-degree, per-night rates by hunting ground. Invented for the demo.
const BASE_RATE: Record<Exclude<HuntingGround, null> | "none", Partial<Record<CatchType, number>>> = {
  solar: { asteroid: 1.2, near_earth_object: 0.01, trans_neptunian_object: 0.004, comet: 0.0008, variable_star: 0.3, flare: 0.02, supernova: 0.004, unknown: 0.01 },
  bulge: { microlensing: 0.03, variable_star: 2.5, flare: 0.4, eclipsing_binary: 0.6, asteroid: 0.05, unknown: 0.03 },
  deep: { supernova: 0.02, active_galaxy: 0.05, tidal_disruption_event: 0.0004, kilonova: 0.00002, variable_star: 0.2, unknown: 0.01 },
  none: { variable_star: 0.4, flare: 0.05, supernova: 0.008, active_galaxy: 0.01, asteroid: 0.02, unknown: 0.01 },
};

const RARE: Partial<Record<CatchType, number>> = {
  interstellar_object: 2e-8,
  planet_candidate: 2e-5,
  eclipsing_binary: 0.01,
};

const BANDS = ["u", "g", "r", "i", "z", "y"];

// Visit likelihood per night by footprint region, loosely following the survey's emphasis.
const REGION_NIGHTLY: Record<string, number> = {
  lowdust: 0.22,
  virgo: 0.2,
  euclid_overlap: 0.18,
  bulgy: 0.14,
  LMC_SMC: 0.14,
  nes: 0.1,
  scp: 0.08,
  dusty_plane: 0.07,
  outside: 0,
};

export function mockForecast(
  sphere: Sphere,
  win: ForecastWindow,
  footprintLabel: string,
  now: Date = new Date(),
): Forecast {
  const rand = rng(seedOf(sphere));
  const nights = win === "tonight" ? 1 : 7;
  const start = now;
  const end = new Date(now.getTime() + nights * 24 * 3600 * 1000);

  const nightly = (REGION_NIGHTLY[footprintLabel] ?? 0.1) * (0.8 + 0.4 * rand());
  const pVisit = footprintLabel === "outside" ? 0 : 1 - (1 - nightly) ** nights;

  const visits: Forecast["visits"] = [];
  if (pVisit > 0) {
    let t = now.getTime() + (0.5 + rand() * 9) * 3600 * 1000;
    while (t < end.getTime() && visits.length < 12) {
      visits.push({ time: new Date(t).toISOString(), band: BANDS[Math.floor(rand() * BANDS.length)] });
      // Rubin revisits a field ~33 minutes later for a pair, then days later.
      t += visits.length % 2 === 1 ? 33 * 60 * 1000 : (1 + rand() * 3) * 24 * 3600 * 1000;
    }
  }

  const ground = huntingGround(sphere.ra_deg, sphere.dec_deg) ?? "none";
  const area = capAreaDeg2(sphere.radius_deg);
  const exposure = Math.max(visits.length, pVisit > 0 ? 1 : 0.05);
  const rates = { ...BASE_RATE[ground], ...RARE };
  const expected = (Object.entries(rates) as [CatchType, number][])
    .map(([type, rate]) => ({
      type,
      mean_count: Number((rate * area * exposure * (0.6 + 0.8 * rand()) * (pVisit > 0 ? 1 : 0.1)).toPrecision(3)),
    }))
    .filter((e) => e.mean_count > 0)
    .sort((a, b) => b.mean_count - a.mean_count);

  const known: Forecast["known_solar_system_objects"] = [];
  if (Math.abs(eclipticLatitude(sphere.ra_deg, sphere.dec_deg)) < 12) {
    const n = Math.min(6, Math.floor(area * 0.4 * rand()) + (rand() < 0.5 ? 1 : 0));
    for (let i = 0; i < n; i++) {
      const a = rand() * 2 * Math.PI;
      const r = Math.sqrt(rand()) * sphere.radius_deg;
      known.push({
        name: `Demo asteroid ${i + 1}`,
        type: "asteroid",
        ra_deg: (sphere.ra_deg + (r * Math.cos(a)) / Math.max(0.1, Math.cos((sphere.dec_deg * Math.PI) / 180)) + 360) % 360,
        dec_deg: Math.max(-90, Math.min(90, sphere.dec_deg + r * Math.sin(a))),
      });
    }
  }

  return {
    sphere,
    window: { start: start.toISOString(), end: end.toISOString() },
    rubin_visit_probability: Number(pVisit.toFixed(3)),
    visits,
    expected,
    known_solar_system_objects: known,
    generated_at: now.toISOString(),
    inputs_used: ["demo data: seeded mock in web/src/mock/forecast.ts", `footprint region: ${footprintLabel}`],
  };
}

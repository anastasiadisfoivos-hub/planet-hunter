// The physics behind "Measure its planet" and "Kepler check": a simple transit model and Kepler's
// third law. Pure functions, tested in tests/lab/transit.test.ts.

/** Astronomical unit in solar radii (IAU 2012 au / IAU 2015 nominal solar radius). */
export const AU_PER_RSUN = 149597870.7 / 695700;
/** Solar radius in Earth radii (equatorial, 6,378.1 km). */
export const REARTH_PER_RSUN = 695700 / 6378.137;
/** Solar radius in Jupiter radii (equatorial, 71,492 km). */
export const RJUP_PER_RSUN = 695700 / 71492;
export const DAYS_PER_YEAR = 365.25;

/**
 * Kepler's third law in the units that make it simple: orbit size in AU from the star's mass in Suns
 * and the planet's year in Earth years. a = ∛(M·P²). (The planet's own mass is left out.)
 */
export function keplerAu(massSun: number, periodDays: number): number {
  const p = periodDays / DAYS_PER_YEAR;
  return Math.cbrt(massSun * p * p);
}

/** Orbit size in units of the star's radius, a/R★. */
export function aOverR(aAu: number, starRadiusSun: number): number {
  return (aAu * AU_PER_RSUN) / starRadiusSun;
}

/**
 * Fraction of a uniformly bright star (radius 1) hidden by a planet of radius k whose centre is z
 * star radii from the star's centre. Exact circle-overlap area over π.
 */
export function coveredFraction(z: number, k: number): number {
  if (k <= 0 || z >= 1 + k) return 0;
  if (z <= k - 1) return 1; // planet bigger than the star, covering it
  if (z <= 1 - k) return k * k; // whole planet inside the disk
  const k0 = Math.acos(Math.min(1, Math.max(-1, (k * k + z * z - 1) / (2 * k * z))));
  const k1 = Math.acos(Math.min(1, Math.max(-1, (1 - k * k + z * z) / (2 * z))));
  const s = Math.max(0, 4 * z * z - (1 + z * z - k * k) ** 2);
  return (k * k * k0 + k1 - 0.5 * Math.sqrt(s)) / Math.PI;
}

/** Impact parameter: how far from the star's centre the planet crosses, in star radii. */
export function impactParameter(aR: number, inclinationDeg: number): number {
  return aR * Math.cos((inclinationDeg * Math.PI) / 180);
}

/** The inclination at which the planet only just grazes the star's edge (b = 1 + k). */
export function grazingInclination(aR: number, k: number): number {
  return (Math.acos(Math.min(1, (1 + k) / aR)) * 180) / Math.PI;
}

export type TransitModel = { k: number; aR: number; inclinationDeg: number };

/**
 * Relative brightness at a phase (fraction of an orbit from mid-transit, -0.5 to 0.5) for a circular
 * orbit. The star is an evenly bright disk: no limb darkening, so the bottom of the dip is flat.
 */
export function transitFlux(phase: number, m: TransitModel): number {
  const th = 2 * Math.PI * phase;
  if (Math.cos(th) <= 0) return 1; // behind the star
  const x = m.aR * Math.sin(th);
  const y = m.aR * Math.cos(th) * Math.cos((m.inclinationDeg * Math.PI) / 180);
  return 1 - coveredFraction(Math.hypot(x, y), m.k);
}

/** Deepest point of the dip, as a fraction of the star's light. */
export function modelDepth(m: TransitModel): number {
  return 1 - transitFlux(0, m);
}

/** Root-mean-square gap between data and model, in parts per million. */
export function rmsPpm(phase: number[], flux: number[], m: TransitModel): number {
  if (!phase.length) return NaN;
  let s = 0;
  for (let i = 0; i < phase.length; i++) s += (flux[i] - transitFlux(phase[i], m)) ** 2;
  return Math.sqrt(s / phase.length) * 1e6;
}

/** Planet radius from Rp/R★ and the star's radius. */
export function planetRadius(k: number, starRadiusSun: number): { earth: number; jupiter: number } {
  const rSun = k * starRadiusSun;
  return { earth: rSun * REARTH_PER_RSUN, jupiter: rSun * RJUP_PER_RSUN };
}

/** Rp/R★ that makes a uniform-disk dip of this depth (depth = k²). */
export function kFromDepth(depth: number): number {
  return Math.sqrt(Math.max(0, depth));
}

// Rough main-sequence masses by temperature, for stars whose mass is not listed.
const MS: [number, number][] = [
  [2600, 0.09], [3000, 0.2], [3500, 0.4], [4000, 0.6], [4500, 0.7], [5000, 0.8], [5500, 0.9], [5772, 1],
  [6000, 1.1], [6500, 1.3], [7000, 1.5], [8000, 1.8], [10000, 2.5], [15000, 4], [20000, 7], [30000, 15],
];

/** Mass in Suns guessed from temperature, assuming a main-sequence star. An estimate only. */
export function massFromTeff(teff: number): number {
  if (teff <= MS[0][0]) return MS[0][1];
  for (let i = 1; i < MS.length; i++) {
    const [t1, m1] = MS[i];
    if (teff <= t1) {
      const [t0, m0] = MS[i - 1];
      return m0 + ((m1 - m0) * (teff - t0)) / (t1 - t0);
    }
  }
  return MS[MS.length - 1][1];
}

/** How close a guess is, as a ratio: 1.12 means 12% too big; 0.9 means 10% too small. */
export function guessRatio(guess: number, truth: number): number {
  return guess / truth;
}

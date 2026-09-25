// The physics behind the Lab experiments: blackbody light, star colour, visible colour of a
// wavelength, the Hubble law, and light-curve folding. Pure functions, tested in tests/lab.

import { starColor, type Rgb } from "../../lib/starColor.ts";

/** Wien's displacement constant, nm·K (CODATA 2018). */
export const WIEN_B_NM_K = 2.897771955e6;
const H = 6.62607015e-34; // Planck, J s
const C = 299792458; // speed of light, m/s
const K = 1.380649e-23; // Boltzmann, J/K
/** Speed of light in km/s, for v = cz. */
export const C_KMS = 299792.458;
/** The Sun's effective temperature (IAU 2015 nominal), K. */
export const SUN_TEFF = 5772;

/** Wavelength where a blackbody at T kelvin is brightest, in nanometres. */
export function wienPeakNm(teff: number): number {
  return WIEN_B_NM_K / teff;
}

/** Planck spectral radiance B(λ, T) in W sr⁻¹ m⁻³ for a wavelength in nm. */
export function planck(nm: number, teff: number): number {
  const l = nm * 1e-9;
  const x = (H * C) / (l * K * teff);
  if (x > 700) return 0;
  return (2 * H * C * C) / l ** 5 / Math.expm1(x);
}

/** Planck curve sampled on [fromNm, toNm], scaled so its own peak is 1. */
export function blackbodyCurve(teff: number, fromNm: number, toNm: number, n: number): { nm: number[]; value: number[] } {
  const peak = planck(wienPeakNm(teff), teff);
  const nm: number[] = [];
  const value: number[] = [];
  for (let i = 0; i < n; i++) {
    const w = fromNm + ((toNm - fromNm) * i) / (n - 1);
    nm.push(w);
    value.push(planck(w, teff) / peak);
  }
  return { nm, value };
}

/** How much more blue light (450 nm) than red light (650 nm) a blackbody gives off. Above 1: bluer. */
export function blueRedRatio(teff: number): number {
  return planck(450, teff) / planck(650, teff);
}

/** Total light per square metre relative to the Sun (Stefan-Boltzmann, T⁴). */
export function surfaceBrightnessVsSun(teff: number): number {
  return (teff / SUN_TEFF) ** 4;
}

/** The colour a star of this temperature is drawn in on the map (same function, same boost). */
export function temperatureColor(teff: number): Rgb {
  return starColor(teff);
}

export function rgbCss(c: Rgb): string {
  return `rgb(${c.map((v) => Math.round(v * 255)).join(" ")})`;
}

/**
 * Approximate display colour of a single visible wavelength (380 to 750 nm), after Dan Bruton's
 * piecewise model, with intensity falling off at the edges of vision. Outside the band: black.
 */
export function wavelengthRgb(nm: number): Rgb {
  let r = 0;
  let g = 0;
  let b = 0;
  if (nm >= 380 && nm < 440) {
    r = (440 - nm) / 60;
    b = 1;
  } else if (nm < 490) {
    g = (nm - 440) / 50;
    b = 1;
  } else if (nm < 510) {
    g = 1;
    b = (510 - nm) / 20;
  } else if (nm < 580) {
    r = (nm - 510) / 70;
    g = 1;
  } else if (nm < 645) {
    r = 1;
    g = (645 - nm) / 65;
  } else if (nm <= 750) {
    r = 1;
  }
  let f = 0;
  if (nm >= 380 && nm < 420) f = 0.3 + (0.7 * (nm - 380)) / 40;
  else if (nm >= 420 && nm <= 700) f = 1;
  else if (nm > 700 && nm <= 750) f = 0.3 + (0.7 * (750 - nm)) / 50;
  const gamma = 0.8;
  return [r, g, b].map((v) => (v > 0 ? (v * f) ** gamma : 0)) as Rgb;
}

// ---------- Hubble diagram ----------

/** Peak absolute magnitude of a type Ia supernova (the standard candle), roughly. */
export const SN_IA_ABS_MAG = -19.3;

/** Distance in megaparsecs from apparent peak magnitude m, for a candle of absolute magnitude M. */
export function distanceMpc(m: number, absMag = SN_IA_ABS_MAG): number {
  return 10 ** ((m - absMag - 25) / 5);
}

/** Apparent magnitude of the candle at a distance in megaparsecs. */
export function apparentMag(dMpc: number, absMag = SN_IA_ABS_MAG): number {
  return absMag + 25 + 5 * Math.log10(dMpc);
}

/** Recession speed in km/s from redshift (v = cz, fine for nearby galaxies, z below about 0.1). */
export function speedKms(z: number): number {
  return C_KMS * z;
}

/** H0 in km/s/Mpc for a line through the origin and one point (distance, speed). */
export function h0FromPoint(dMpc: number, vKms: number): number {
  return vKms / dMpc;
}

/** Least-squares slope through the origin: the best-fit H0 for points (d, v). */
export function fitH0(points: { d: number; v: number }[]): number {
  let sxy = 0;
  let sxx = 0;
  for (const p of points) {
    sxy += p.d * p.v;
    sxx += p.d * p.d;
  }
  return sxx > 0 ? sxy / sxx : NaN;
}

/** Root-mean-square scatter of speeds about the line v = H0 d, km/s. */
export function rmsResidual(points: { d: number; v: number }[], h0: number): number {
  if (!points.length) return NaN;
  return Math.sqrt(points.reduce((a, p) => a + (p.v - h0 * p.d) ** 2, 0) / points.length);
}

/** Hubble time 1/H0 in billions of years: a rough age of the universe. */
export function hubbleTimeGyr(h0: number): number {
  return 977.792 / h0;
}

// ---------- Light curves and sound ----------

/** Phase in [-0.5, 0.5) with the transit (t0) at 0. */
export function phaseOf(t: number, period: number, t0: number): number {
  const p = (((t - t0) / period) % 1 + 1) % 1;
  return p >= 0.5 ? p - 1 : p;
}

/** Fold a light curve on a period and average it into equal phase bins (empty bins are dropped). */
export function foldAndBin(time: number[], flux: number[], period: number, t0: number, bins: number): { phase: number[]; flux: number[] } {
  const sum = new Float64Array(bins);
  const n = new Uint32Array(bins);
  for (let i = 0; i < time.length; i++) {
    const k = Math.min(bins - 1, Math.floor((phaseOf(time[i], period, t0) + 0.5) * bins));
    sum[k] += flux[i];
    n[k]++;
  }
  const phase: number[] = [];
  const out: number[] = [];
  for (let k = 0; k < bins; k++) {
    if (!n[k]) continue;
    phase.push((k + 0.5) / bins - 0.5);
    out.push(sum[k] / n[k]);
  }
  return { phase, flux: out };
}

/**
 * Pitch for a brightness: the star's brightest level plays `high` Hz, its faintest `low` Hz, on a
 * musical (logarithmic) scale in between. Dips in brightness are heard as drops in pitch.
 */
export function pitchFor(flux: number, minFlux: number, maxFlux: number, low = 196, high = 784): number {
  const f = maxFlux > minFlux ? Math.min(1, Math.max(0, (flux - minFlux) / (maxFlux - minFlux))) : 1;
  return low * (high / low) ** f;
}

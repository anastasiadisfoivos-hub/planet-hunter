// The Sun's apparent RA/Dec for a moment in time. Low-precision formula from the Astronomical
// Almanac (good to about 0.01 degree for 1950 to 2050), plenty for placing a marker on the sky.

const DEG = Math.PI / 180;

/** Julian date from a JS time in milliseconds. */
export function julianDate(ms: number): number {
  return ms / 86400000 + 2440587.5;
}

export function sunRaDec(ms: number): { ra: number; dec: number } {
  const n = julianDate(ms) - 2451545.0;
  const L = (280.46 + 0.9856474 * n) % 360;
  const g = ((357.528 + 0.9856003 * n) % 360) * DEG;
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * DEG;
  const eps = (23.439 - 0.0000004 * n) * DEG;
  let ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda)) / DEG;
  if (ra < 0) ra += 360;
  return { ra, dec: Math.asin(Math.sin(eps) * Math.sin(lambda)) / DEG };
}

// Sky geometry. Dependency free so build scripts can import it too.
//
// Scene axes (equatorial, ICRS): +y = north celestial pole, +x = RA 0h, -z = RA 6h.
// Seen from Earth at the origin, RA then increases to the left when facing the sky, as on the real sky.

export const DEG = Math.PI / 180;

export type Vec3 = [number, number, number];

export function radecToVec(raDeg: number, decDeg: number): Vec3 {
  const ra = raDeg * DEG;
  const dec = decDeg * DEG;
  const c = Math.cos(dec);
  return [c * Math.cos(ra), Math.sin(dec), -c * Math.sin(ra)];
}

export function vecToRadec(v: Vec3): { ra: number; dec: number } {
  const [x, y, z] = v;
  const r = Math.hypot(x, y, z) || 1;
  let ra = Math.atan2(-z, x) / DEG;
  if (ra < 0) ra += 360;
  return { ra, dec: Math.asin(Math.max(-1, Math.min(1, y / r))) / DEG };
}

export function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/** Great-circle separation in degrees between two unit vectors. */
export function separationDeg(a: Vec3, b: Vec3): number {
  // atan2 form stays accurate for the 0.05 degree traps, where acos loses precision.
  const cx = a[1] * b[2] - a[2] * b[1];
  const cy = a[2] * b[0] - a[0] * b[2];
  const cz = a[0] * b[1] - a[1] * b[0];
  return Math.atan2(Math.hypot(cx, cy, cz), dot(a, b)) / DEG;
}

// Rotation from ICRS equatorial (standard x,y,z with z = north pole) to galactic.
// Rows are the galactic x, y, z axes expressed in equatorial coordinates (Hipparcos, ESA 1997).
const EQ_TO_GAL = [
  [-0.0548755604, -0.8734370902, -0.4838350155],
  [0.4941094279, -0.44482963, 0.7469822445],
  [-0.867666149, -0.1980763734, 0.4559837762],
];

/** Standard astronomical unit vector (z = north pole) from ra/dec. */
function astroVec(raDeg: number, decDeg: number): Vec3 {
  const ra = raDeg * DEG;
  const dec = decDeg * DEG;
  return [Math.cos(dec) * Math.cos(ra), Math.cos(dec) * Math.sin(ra), Math.sin(dec)];
}

export function galactic(raDeg: number, decDeg: number): { l: number; b: number } {
  const v = astroVec(raDeg, decDeg);
  const g = EQ_TO_GAL.map((row) => row[0] * v[0] + row[1] * v[1] + row[2] * v[2]);
  let l = Math.atan2(g[1], g[0]) / DEG;
  if (l < 0) l += 360;
  return { l, b: Math.asin(g[2]) / DEG };
}

const OBLIQUITY = 23.4392911 * DEG;

export function eclipticLatitude(raDeg: number, decDeg: number): number {
  const [, y, z] = astroVec(raDeg, decDeg);
  return Math.asin(z * Math.cos(OBLIQUITY) - y * Math.sin(OBLIQUITY)) / DEG;
}

/** Solid angle of a spherical cap, in square degrees. */
export function capAreaDeg2(radiusDeg: number): number {
  return 2 * Math.PI * (1 - Math.cos(radiusDeg * DEG)) * (180 / Math.PI) ** 2;
}

export type HuntingGround = "solar" | "bulge" | "deep" | null;

/** The layer's three hunting grounds. Order matters: bulge wins over ecliptic where they cross. */
export function huntingGround(raDeg: number, decDeg: number): HuntingGround {
  const { l, b } = galactic(raDeg, decDeg);
  const lw = l > 180 ? l - 360 : l;
  if (Math.abs(lw) < 20 && Math.abs(b) < 12) return "bulge";
  if (Math.abs(eclipticLatitude(raDeg, decDeg)) < 10) return "solar";
  if (Math.abs(b) > 30) return "deep";
  return null;
}

export function formatRa(raDeg: number): string {
  const h = raDeg / 15;
  const hh = Math.floor(h);
  const mm = Math.floor((h - hh) * 60);
  return `${String(hh).padStart(2, "0")}h ${String(mm).padStart(2, "0")}m`;
}

export function formatDec(decDeg: number): string {
  const s = decDeg < 0 ? "-" : "+";
  return `${s}${Math.abs(decDeg).toFixed(1)}°`;
}

export function formatRadius(r: number): string {
  if (r < 1) return `${(r * 60).toFixed(r < 0.1 ? 1 : 0)}′`;
  return `${r.toFixed(r < 3 ? 2 : 1)}°`;
}

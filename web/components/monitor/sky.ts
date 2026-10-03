// The all-sky map's geometry (DESIGN.md: /log). Mollweide, equal-area, centred on RA 0h with RA increasing to the
// left as when looking up; the galactic plane and the ecliptic as lines in the same frame.
// No React and no "@/" value imports, so node --test can load it directly.

const D = Math.PI / 180;

/** Mollweide x in [-2, 2], y in [-1, 1] (y up), for RA and Dec in degrees. */
export function mollweide(raDeg: number, decDeg: number): [number, number] {
  let lon = ((raDeg + 180) % 360 + 360) % 360 - 180; // -180..180, 0h in the middle
  lon = -lon; // RA grows to the left
  const phi = decDeg * D;
  let t = phi;
  if (Math.abs(Math.abs(phi) - Math.PI / 2) < 1e-9) t = phi;
  else {
    for (let i = 0; i < 30; i++) {
      const dt = (2 * t + Math.sin(2 * t) - Math.PI * Math.sin(phi)) / (2 + 2 * Math.cos(2 * t));
      t -= dt;
      if (Math.abs(dt) < 1e-10) break;
    }
  }
  return [(2 / Math.PI) * lon * D * Math.cos(t), Math.sin(t)];
}

/** Galactic (l, b) to equatorial (RA, Dec), J2000, degrees. */
export function galacticToEquatorial(l: number, b: number): [number, number] {
  const lr = l * D;
  const br = b * D;
  const x = Math.cos(br) * Math.cos(lr);
  const y = Math.cos(br) * Math.sin(lr);
  const z = Math.sin(br);
  // transpose of the equatorial-to-galactic rotation (Hipparcos, ESA 1997)
  const X = -0.0548755604 * x + 0.4941094279 * y - 0.867666149 * z;
  const Y = -0.8734370902 * x - 0.44482963 * y - 0.1980763734 * z;
  const Z = -0.4838350155 * x + 0.7469822445 * y + 0.4559837762 * z;
  return [((Math.atan2(Y, X) / D) + 360) % 360, Math.asin(Math.max(-1, Math.min(1, Z))) / D];
}

/** Ecliptic (lambda, beta) to equatorial, J2000 obliquity. */
export function eclipticToEquatorial(lam: number, beta: number): [number, number] {
  const e = 23.4393 * D;
  const l = lam * D;
  const b = beta * D;
  const dec = Math.asin(Math.sin(b) * Math.cos(e) + Math.cos(b) * Math.sin(e) * Math.sin(l));
  const ra = Math.atan2(Math.sin(l) * Math.cos(e) - Math.tan(b) * Math.sin(e), Math.cos(l));
  return [((ra / D) + 360) % 360, dec / D];
}

/**
 * Project a line of sky points into SVG path data in a box of width W (height W/2), lifting the pen wherever the
 * line crosses the map's seam at RA 12h.
 */
export function skyPath(points: [number, number][], W: number, close = false): string {
  const H = W / 2;
  let d = "";
  let prev: [number, number] | null = null;
  const out = (p: [number, number]): [number, number] => [(p[0] + 2) * (W / 4), (1 - p[1]) * (H / 2)];
  for (const [ra, dec] of close ? [...points, points[0]] : points) {
    const q = out(mollweide(ra, dec));
    const jump = prev && Math.abs(q[0] - prev[0]) > W / 3;
    d += `${!prev || jump ? "M" : "L"}${q[0].toFixed(1)} ${q[1].toFixed(1)}`;
    prev = q;
  }
  return d;
}

export function skyXY(ra: number, dec: number, W: number): [number, number] {
  const [x, y] = mollweide(ra, dec);
  return [(x + 2) * (W / 4), (1 - y) * (W / 4)];
}

const range = (a: number, b: number, step: number) => Array.from({ length: Math.round((b - a) / step) + 1 }, (_, i) => a + i * step);

/** The galactic plane (b = 0) and the Milky Way's edges (b = ±10°), as sky points. */
export const galacticLine = (b: number) => range(0, 360, 2).map((l) => galacticToEquatorial(l, b));
export const eclipticLine = () => range(0, 360, 2).map((l) => eclipticToEquatorial(l, 0));

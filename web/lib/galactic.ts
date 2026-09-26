// Sky geometry for the real all-sky photograph (ESO's eso0932a, "ESO/S. Brunier", CC BY 4.0).
//
// The panorama is equirectangular in GALACTIC coordinates: the galactic centre (l = 0, b = 0) is the middle of the
// image, galactic longitude increases to the LEFT, and the image spans l = 180° at both edges, b = +90° at the top.
// Everything else in the app is in ICRS right ascension and declination, so every placement goes through
// raDecToGalactic. Constellation lines, names and boundaries come from d3-celestial (BSD-3-Clause,
// public/data/sky/LICENSE-d3-celestial.txt), in degrees with longitudes in -180..180.

import { galactic } from "./sky.ts";

export type Galactic = { l: number; b: number };

/** ICRS (degrees) to galactic longitude 0..360 and latitude -90..90 (degrees). One conversion for the whole app: lib/sky.ts. */
export function raDecToGalactic(raDeg: number, decDeg: number): Galactic {
  return galactic(raDeg, decDeg);
}

/** Position on the panorama as fractions: u 0..1 left to right, v 0..1 top to bottom. */
export function panoUV(raDeg: number, decDeg: number): { u: number; v: number } {
  const { l, b } = raDecToGalactic(raDeg, decDeg);
  return { u: (((180 - l) % 360) + 360) % 360 / 360, v: (90 - b) / 180 };
}

/** Pixel position on a W × H panorama. */
export function panoXY(raDeg: number, decDeg: number, W: number, H: number): { x: number; y: number } {
  const { u, v } = panoUV(raDeg, decDeg);
  return { x: u * W, y: v * H };
}

// ---------- Constellations ----------

type Position = [number, number];
export type LinesData = { features: { id: string; geometry: { type: "MultiLineString"; coordinates: Position[][] } }[] };
export type NamesData = { features: { id: string; properties: { name: string; rank: string }; geometry: { type: "Point"; coordinates: Position } }[] };
export type BoundsData = { features: { id: string; geometry: { type: "Polygon" | "MultiPolygon"; coordinates: Position[][] | Position[][][] } }[] };

const ra360 = (lon: number) => ((lon % 360) + 360) % 360;

/** Ray casting on one ring, with the ring unwrapped in RA so edges never jump across the 0/360 seam. */
function inRing(ring: Position[], ra: number, dec: number): boolean {
  const pts: Position[] = [[ring[0][0], ring[0][1]]];
  for (let i = 1; i < ring.length; i++) {
    const px = pts[i - 1][0];
    pts.push([px + ((((ring[i][0] - px + 540) % 360) + 360) % 360) - 180, ring[i][1]]);
  }
  const test = (x: number) => {
    let inside = false;
    for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) {
      const [xi, yi] = pts[i];
      const [xj, yj] = pts[j];
      if (yi > dec !== yj > dec && x < xi + ((dec - yi) * (xj - xi)) / (yj - yi)) inside = !inside;
    }
    return inside;
  };
  return [-720, -360, 0, 360, 720].some((k) => test(ra + k));
}

/** The IAU constellation containing a position, by its boundaries. The two polar caps are named directly. */
export function constellationOf(raDeg: number, decDeg: number, bounds: BoundsData, names: NamesData): string | null {
  for (const f of bounds.features) {
    const polys = (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates) as Position[][][];
    if (polys.some((p) => inRing(p[0], raDeg, decDeg))) return names.features.find((n) => n.id === f.id)?.properties.name ?? f.id;
  }
  if (decDeg > 80) return "Ursa Minor";
  if (decDeg < -80) return "Octans";
  return null;
}

/** A window on the panorama in pixels: x0, y0 is its top-left, w × h its size, on a W × H image. */
export type Window = { x0: number; y0: number; w: number; h: number; W: number; H: number };

/** A span of galactic longitude × latitude (degrees) centred on a position, as a pixel window. */
export function windowAround(raDeg: number, decDeg: number, spanL: number, spanB: number, W: number, H: number): Window {
  const { x, y } = panoXY(raDeg, decDeg, W, H);
  const w = (spanL / 360) * W;
  const h = (spanB / 180) * H;
  return { x0: x - w / 2, y0: Math.max(0, Math.min(H - h, y - h / 2)), w, h, W, H };
}

/** x relative to the window's left edge, wrapped so the window never splits at l = 180. */
function wx(x: number, win: Window) {
  if (win.w >= win.W) return x - win.x0;
  const d = ((((x - win.x0 + win.W / 2) % win.W) + win.W) % win.W) - win.W / 2;
  return d;
}

/** SVG path data for the constellation lines inside a window (or the whole panorama). */
export function constellationPath(lines: LinesData, win: Window): string {
  const out: string[] = [];
  const pad = Math.max(win.w, win.h) * 0.1;
  for (const f of lines.features) {
    for (const line of f.geometry.coordinates) {
      const pts = line.map(([lon, lat]) => panoXY(ra360(lon), lat, win.W, win.H));
      for (let i = 1; i < pts.length; i++) {
        const a = pts[i - 1];
        const b = pts[i];
        if (Math.abs(b.x - a.x) > win.W / 2) continue; // the segment crosses l = 180 on the full panorama
        const ax = wx(a.x, win);
        const bx = wx(b.x, win);
        if (Math.abs(bx - ax) > win.W / 2) continue; // it straddles this window's own seam
        const ay = a.y - win.y0;
        const by = b.y - win.y0;
        if (Math.max(ax, bx) < -pad || Math.min(ax, bx) > win.w + pad || Math.max(ay, by) < -pad || Math.min(ay, by) > win.h + pad) continue;
        out.push(`M${ax.toFixed(1)} ${ay.toFixed(1)}L${bx.toFixed(1)} ${by.toFixed(1)}`);
      }
    }
  }
  return out.join("");
}

/** Constellation names (rank ≤ maxRank: 1 major, 2 medium, 3 minor) that fall inside a window. */
export function constellationLabels(names: NamesData, win: Window, maxRank = 3): { name: string; x: number; y: number }[] {
  const out: { name: string; x: number; y: number }[] = [];
  for (const f of names.features) {
    if (Number(f.properties.rank) > maxRank) continue;
    const [lon, lat] = f.geometry.coordinates;
    const p = panoXY(ra360(lon), lat, win.W, win.H);
    const x = wx(p.x, win);
    const y = p.y - win.y0;
    if (x >= 0 && x <= win.w && y >= 0 && y <= win.h) out.push({ name: f.properties.name, x, y });
  }
  return out;
}

/** Bounding box of one constellation's lines on a W × H panorama (for tests and framing). */
export function constellationBox(lines: LinesData, id: string, W: number, H: number) {
  const f = lines.features.find((x) => x.id === id);
  if (!f) return null;
  const pts = f.geometry.coordinates.flat().map(([lon, lat]) => panoXY(ra360(lon), lat, W, H));
  return { x0: Math.min(...pts.map((p) => p.x)), x1: Math.max(...pts.map((p) => p.x)), y0: Math.min(...pts.map((p) => p.y)), y1: Math.max(...pts.map((p) => p.y)) };
}

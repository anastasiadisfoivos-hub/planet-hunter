import * as THREE from "three";
import { radecToVec } from "@/lib/sky";
import { srgbToLinear, starColor } from "@/lib/starColor";

/** Radius of the celestial sphere the sky layers are painted on. */
export const SKY_R = 1000;
/** Event markers sit just inside the star shell. */
export const EVENT_R = 950;
/** Catalogue stars are painted just inside the sky shell. */
export const STAR_R = 975;

/** Camera limits. Zooming in first moves toward Earth, then narrows the field of view. */
export const BASE_FOV = 60;
export const MIN_FOV = 1.5;
export const MIN_DIST = 0.6;

/** Display radius for a host at `pc` parsecs. */
export function sceneDistance(pc: number, trueScale: boolean): number {
  // Log: squeezes 1.3 pc to 4,300 pc into a readable ball. True: 1 unit = 5 pc, linear.
  return trueScale ? pc / 5 : 20 * Math.log10(1 + pc / 2);
}

export function chord(radiusDeg: number): number {
  return 2 * Math.sin((radiusDeg * Math.PI) / 360);
}

export function capUniform(raDeg: number, decDeg: number, radiusDeg: number, out = new THREE.Vector4()): THREE.Vector4 {
  const [x, y, z] = radecToVec(raDeg, decDeg);
  return out.set(x, y, z, chord(radiusDeg));
}

/** Read a CSS custom property as a three.js colour, so tokens.css stays the single source of truth. */
export function tokenColor(name: string, fallback: string): THREE.Color {
  if (typeof window === "undefined") return new THREE.Color(fallback);
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(v || fallback);
}

/**
 * Close-up stars: scene units per solar radius. One scale for every star, so relative sizes are true
 * (a 0.15 R☉ red dwarf is a tenth the size of a 1.5 R☉ F star). Missing radius: drawn at 1 R☉.
 */
export const RSUN_UNITS = 0.004;
export function displayRadius(rsun: number): number {
  return RSUN_UNITS * (rsun > 0 ? rsun : 1);
}

/** Linear colour for a shader from a star's temperature (see lib/starColor.ts). */
export function linearStarColor(teff: number): [number, number, number] {
  const c = starColor(teff);
  return [srgbToLinear(c[0]), srgbToLinear(c[1]), srgbToLinear(c[2])];
}

/** DOM elements the scene writes to directly each frame (no React re-render). */
export const hud: {
  pointer: HTMLElement | null;
  fov: HTMLElement | null;
  fps: HTMLElement | null;
  /** Name label that follows the hovered event or planet host. */
  hover: HTMLElement | null;
  /** Labels that explain the two landmarks: Earth (visible once you zoom out past it) and the Sun. */
  earth: HTMLElement | null;
  sun: HTMLElement | null;
} = { pointer: null, fov: null, fps: null, hover: null, earth: null, sun: null };

/** Commands the UI can send to the scene (set by the scene once mounted). */
export const view: {
  jumpTo: ((ra: number, dec: number, fovDeg: number) => void) | null;
  /** Test hook: CSS-pixel position of (ra, dec) on the canvas, or null when behind the camera. */
  project: ((ra: number, dec: number) => { x: number; y: number } | null) | null;
  bakeInfo: { cubeMs: number; detailMs: number; detailBakes: number; face: number } | null;
} = { jumpTo: null, project: null, bakeInfo: null };

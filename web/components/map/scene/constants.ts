import * as THREE from "three";
import type { Sphere } from "@/lib/contract";
import { radecToVec } from "@/lib/sky";

/** Radius of the celestial sphere the sky layers are painted on. */
export const SKY_R = 1000;
/** Watch bubbles sit just inside the sky, so a bubble of radius D·sin(θ) spans θ as seen from Earth. */
export const WATCH_D = 940;
/** Catalogue stars are painted just inside the sky shell. */
export const STAR_R = 975;

/** Camera limits. Zooming in first moves toward Earth, then narrows the field of view. */
export const BASE_FOV = 55;
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

export function capUniform(s: Sphere, out = new THREE.Vector4()): THREE.Vector4 {
  const [x, y, z] = radecToVec(s.ra_deg, s.dec_deg);
  return out.set(x, y, z, chord(s.radius_deg));
}

/** Read a CSS custom property as a three.js colour, so tokens.css stays the single source of truth. */
export function tokenColor(name: string, fallback: string): THREE.Color {
  if (typeof window === "undefined") return new THREE.Color(fallback);
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return new THREE.Color(v || fallback);
}

/** Star colour from B-V, kept near-neutral so the accent stays reserved for planet hosts. */
export function bvColor(bv: number): [number, number, number] {
  const t = Math.max(-0.4, Math.min(2, bv));
  const warm = (t + 0.4) / 2.4; // 0 blue-white .. 1 orange
  return [0.82 + 0.18 * warm, 0.86 + 0.02 * warm, 1.0 - 0.3 * warm];
}

/**
 * DOM elements the scene writes to directly each frame (no React re-render): the floating
 * readout next to the watch being drawn, and the status bar fields.
 */
export const hud: {
  readout: HTMLElement | null;
  readoutTarget: THREE.Vector3 | null;
  readoutRadius: number;
  pointer: HTMLElement | null;
  fov: HTMLElement | null;
  fps: HTMLElement | null;
} = { readout: null, readoutTarget: null, readoutRadius: 0, pointer: null, fov: null, fps: null };

/** Commands the HUD can send to the scene (set by the scene once mounted). */
export const view: {
  jumpTo: ((ra: number, dec: number, fovDeg: number) => void) | null;
  bakeInfo: { cubeMs: number; detailMs: number; face: number } | null;
} = { jumpTo: null, bakeInfo: null };

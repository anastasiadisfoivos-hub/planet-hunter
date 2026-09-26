// Event markers fade in and out when the filters change instead of popping. Markers that leave stay
// drawn (but not pickable) until they have faded; then they are dropped. Pure, so it is testable.

import type { Marker } from "../../../lib/markers.ts";

/** DESIGN.md, Motion: map markers may fade over up to 240 ms. */
export const MARKER_FADE_S = 0.24;

/** Markers still on screen that the new set no longer contains, newest leavers first, no duplicates. */
export function leavers(prevShown: Marker[], prevLeaving: Marker[], next: Marker[]): Marker[] {
  const keep = new Set(next.map((m) => m.id));
  const seen = new Set<string>();
  const out: Marker[] = [];
  for (const m of [...prevShown, ...prevLeaving]) {
    if (keep.has(m.id) || seen.has(m.id)) continue;
    seen.add(m.id);
    out.push(m);
  }
  return out;
}

/** Longest frame step counted: covers slow frames, but the first frame after a hidden tab resumes the fade. */
export const MAX_DT = 0.1;

/** The DESIGN.md curve, cubic-bezier(.2, 0, 0, 1), close enough for a fade: a strong ease-out. */
export const easeOut = (t: number) => 1 - Math.pow(1 - Math.min(1, Math.max(0, t)), 3);

/**
 * Move each marker's linear progress toward its target (1 for the first `live` markers, 0 for the
 * leavers after them) by `dt` seconds. Writes the eased opacity into `alpha`. Returns whether anything
 * is still moving. `dt` is clamped to MAX_DT, so the first frame after a hidden tab resumes the fade instead of jumping.
 */
export function stepFade(progress: Float32Array, alpha: Float32Array, live: number, dt: number, reduced: boolean): boolean {
  const step = reduced ? 1 : Math.min(dt, MAX_DT) / MARKER_FADE_S;
  let moving = false;
  for (let i = 0; i < progress.length; i++) {
    const target = i < live ? 1 : 0;
    const p = progress[i];
    const next = p < target ? Math.min(target, p + step) : p > target ? Math.max(target, p - step) : p;
    progress[i] = next;
    // Ease out both ways: arriving markers settle in, leaving ones drop away at once.
    alpha[i] = target === 1 ? easeOut(next) : 1 - easeOut(1 - next);
    if (next !== target) moving = true;
  }
  return moving;
}

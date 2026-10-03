// The monitor's trace model (DESIGN.md: The monitor). Pure maths, no DOM: the tape (data time with the gaps
// between sectors shortened), the pen's speed profile, the dips to mark and the flux scale.
// No React and no "@/" value imports, so node --test can load it directly.

import type { Detection, MonitorStar } from "@/lib/api";

/** Tape-days of data drawn per second of wall time. A 27-day sector takes about 12 s. */
export const DAYS_PER_SECOND = 2.2;
/** Seconds to reach full speed at the start of a star, and to stop at its end. */
export const RAMP_S = 0.8;
/** How long the finished trace holds before the paper advances. */
export const HOLD_S = 1.8;
/** The paper advance between stars. */
export const ADVANCE_S = 0.9;
/** A gap in the data longer than this (days) is a break in the line. */
export const GAP_D = 0.75;
/** How long a break is on the tape, whatever its length in time. */
export const BREAK_TAPE_D = 1.5;
/** Where the pen sits across the width. */
export const PEN_AT = 0.72;

export type Segment = {
  /** First and last data time (BTJD) in the segment. */
  t0: number;
  t1: number;
  /** Where t0 sits on the tape (days from the tape's start). */
  x0: number;
  /** Index range into the curve [i0, i1). */
  i0: number;
  i1: number;
  sector: number | null;
};

export type Mark = {
  /** Tape position of the dip's middle. */
  x: number;
  /** Data time of the dip's middle (BTJD). */
  t: number;
  /** Index into star.detections. */
  det: number;
  /** The first dip of this detection gets the labelled tick; later ones a small tick. */
  first: boolean;
  /** Half the dip's duration on the tape, for lighting the line. */
  halfWidth: number;
};

export type Tape = {
  t: Float64Array;
  f: Float32Array;
  /** Tape position of every point. */
  x: Float64Array;
  segments: Segment[];
  length: number;
  marks: Mark[];
  /** Flux shown at the top and bottom of the trace band. */
  yTop: number;
  yBottom: number;
};

/** Sectors in time order, split where the data jumps by more than a sector's gap. */
function sectorOf(t: number, sectors: number[], bounds: [number, number][]): number | null {
  const k = bounds.findIndex(([a, b]) => t >= a - 1 && t <= b + 1);
  return k >= 0 ? (sectors[k] ?? null) : null;
}

export function buildTape(star: Pick<MonitorStar, "lightcurve" | "detections" | "sectors">): Tape {
  const lc = star.lightcurve ?? { t: [], f: [] };
  const n = lc.t.length;
  const t = Float64Array.from(lc.t);
  const f = Float32Array.from(lc.f);
  const x = new Float64Array(n);
  const segments: Segment[] = [];
  let start = 0;
  let pos = 0;
  for (let i = 1; i <= n; i++) {
    if (i === n || t[i] - t[i - 1] > GAP_D) {
      if (i > start) {
        const x0 = pos;
        for (let k = start; k < i; k++) x[k] = x0 + (t[k] - t[start]);
        segments.push({ t0: t[start], t1: t[i - 1], x0, i0: start, i1: i, sector: null });
        pos = x0 + (t[i - 1] - t[start]) + BREAK_TAPE_D;
      }
      start = i;
    }
  }
  const length = segments.length ? pos - BREAK_TAPE_D : 0;

  // Label each break with its sector: the big jumps (weeks or more) separate sectors; small ones are
  // the mid-sector download gap.
  const bigGaps = segments.filter((s, k) => k === 0 || s.t0 - segments[k - 1].t1 > 10);
  const bounds: [number, number][] = bigGaps.map((s) => {
    const k = segments.indexOf(s);
    let end = segments.length - 1;
    for (let j = k + 1; j < segments.length; j++) {
      if (segments[j].t0 - segments[j - 1].t1 > 10) {
        end = j - 1;
        break;
      }
    }
    return [s.t0, segments[end].t1];
  });
  const sectors = [...star.sectors].sort((a, b) => a - b);
  for (const s of segments) s.sector = bounds.length === sectors.length ? sectorOf(s.t0, sectors, bounds) : null;

  const marks = buildMarks(star.detections, segments);
  const [yTop, yBottom] = fluxRange(f, star.detections);
  return { t, f, x, segments, length, marks, yTop, yBottom };
}

/** Data time to tape position; times in a gap map to the gap's start. */
export function tapeX(tape: Pick<Tape, "segments">, time: number): number | null {
  for (const s of tape.segments) {
    if (time >= s.t0 && time <= s.t1) return s.x0 + (time - s.t0);
  }
  return null;
}

/** Mid-transit times of a detection that fall inside the data. */
export function dipTimes(d: Detection, segments: Segment[]): number[] {
  if (!segments.length) return [];
  const lo = segments[0].t0;
  const hi = segments[segments.length - 1].t1;
  const out: number[] = [];
  const inData = (tm: number) => segments.some((s) => tm >= s.t0 && tm <= s.t1);
  if (d.period_d == null || d.kind === "single") {
    if (inData(d.t0)) out.push(d.t0);
    return out;
  }
  const P = d.period_d;
  const first = Math.ceil((lo - d.t0) / P);
  for (let k = first; d.t0 + k * P <= hi; k++) {
    const tm = d.t0 + k * P;
    if (inData(tm)) out.push(tm);
    if (out.length > 4000) break;
  }
  return out;
}

function buildMarks(dets: Detection[], segments: Segment[]): Mark[] {
  const marks: Mark[] = [];
  dets.forEach((d, det) => {
    const times = dipTimes(d, segments);
    times.forEach((tm, j) => {
      const xm = tapeX({ segments }, tm);
      if (xm == null) return;
      marks.push({ x: xm, t: tm, det, first: j === 0, halfWidth: d.duration_h / 48 });
    });
  });
  return marks.sort((a, b) => a.x - b.x);
}

/**
 * The flux range the band shows: the middle 99.6% of points, widened to hold the deepest dip the search
 * found, with a little air. One scale per star, so the line never rescales while it draws.
 */
export function fluxRange(f: ArrayLike<number>, dets: Detection[]): [number, number] {
  if (!f.length) return [1.001, 0.999];
  const s = Array.from(f).filter(Number.isFinite).sort((a, b) => a - b);
  const q = (p: number) => s[Math.min(s.length - 1, Math.max(0, Math.round(p * (s.length - 1))))];
  let lo = q(0.002);
  const hi = q(0.998);
  const deepest = Math.max(0, ...dets.map((d) => d.depth_ppm ?? 0)) * 1e-6;
  if (deepest > 0) lo = Math.min(lo, 1 - deepest * 1.08);
  const span = Math.max(hi - lo, 4e-4);
  return [hi + span * 0.12, lo - span * 0.12];
}

/** Seconds the pen takes over a tape of `length` days, ramps included. */
export function drawSeconds(length: number, v = DAYS_PER_SECOND, ramp = RAMP_S): number {
  if (length <= 0) return 0;
  const cruise = length / v - ramp;
  if (cruise >= 0) return length / v + ramp;
  // Too short to reach full speed: accelerate for half, decelerate for half.
  return 2 * Math.sqrt((length * ramp) / v);
}

/**
 * Where the pen is on the tape after `elapsed` seconds: a trapezoid speed profile (speed up over `ramp`,
 * cruise at `v`, slow down over `ramp`). Data time itself runs linearly; only the start and stop ease.
 */
export function penAt(elapsed: number, length: number, v = DAYS_PER_SECOND, ramp = RAMP_S): number {
  if (length <= 0) return 0;
  const T = drawSeconds(length, v, ramp);
  const e = Math.min(Math.max(elapsed, 0), T);
  if (length / v - ramp < 0) {
    const a = length / ((T / 2) * (T / 2));
    return e <= T / 2 ? 0.5 * a * e * e : length - 0.5 * a * (T - e) * (T - e);
  }
  if (e < ramp) return (v * e * e) / (2 * ramp);
  if (e > T - ramp) return length - (v * (T - e) * (T - e)) / (2 * ramp);
  return v * (e - ramp / 2);
}

/** Marks the pen has passed at `x`, in order. */
export function marksReached(tape: Pick<Tape, "marks">, x: number): Mark[] {
  const out: Mark[] = [];
  for (const m of tape.marks) {
    if (m.x > x) break;
    out.push(m);
  }
  return out;
}

/** First index with x[i] >= v (binary search). */
export function lowerBound(xs: ArrayLike<number>, v: number): number {
  let lo = 0;
  let hi = xs.length;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (xs[mid] < v) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** The phases of a star on the monitor, from the time since it started. */
export type Phase = { kind: "drawing"; x: number } | { kind: "holding" } | { kind: "advancing"; p: number } | { kind: "done" };

export function phaseAt(elapsed: number, length: number): Phase {
  const T = drawSeconds(length);
  if (elapsed < T) return { kind: "drawing", x: penAt(elapsed, length) };
  if (elapsed < T + HOLD_S) return { kind: "holding" };
  if (elapsed < T + HOLD_S + ADVANCE_S) return { kind: "advancing", p: (elapsed - T - HOLD_S) / ADVANCE_S };
  return { kind: "done" };
}

/** The paper advance's easing (DESIGN.md --ease-in-out, cubic-bezier(0.65, 0, 0.35, 1), approximated). */
export function easeInOut(p: number): number {
  const c = Math.min(Math.max(p, 0), 1);
  return c < 0.5 ? 4 * c * c * c : 1 - Math.pow(-2 * c + 2, 3) / 2;
}

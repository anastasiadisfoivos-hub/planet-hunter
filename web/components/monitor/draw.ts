// Hand-written 2D canvas drawing for the monitor (DESIGN.md: The monitor). One function per layer:
// the paper's grid, the margin lane's marks, the trace, the pen. The caller owns the frame loop.

import type { Detection, DetectionOutcome } from "@/lib/api";
import { btjdToMs, detectionLabel, fmtDay } from "./format";
import { lowerBound, type Mark, type Tape } from "./trace";

export type Ink = {
  paper: string;
  ink: string;
  ink2: string;
  ink3: string;
  pen: string;
  known: string;
  grid: string;
  gridStrong: string;
  wash: string;
  mono: string;
};

/** Read the palette from the CSS tokens on `el`, so the canvas follows the theme and forced colours. */
export function readInk(el: Element): Ink {
  const cs = getComputedStyle(el);
  const v = (name: string, fallback: string) => cs.getPropertyValue(name).trim() || fallback;
  const forced = typeof matchMedia === "function" && matchMedia("(forced-colors: active)").matches;
  if (forced) {
    return { paper: "Canvas", ink: "CanvasText", ink2: "CanvasText", ink3: "GrayText", pen: "Highlight", known: "LinkText", grid: "transparent", gridStrong: "GrayText", wash: "transparent", mono: v("--mono", "monospace") };
  }
  return {
    paper: v("--paper", "#ede8dc"),
    ink: v("--ink", "#1c1a16"),
    ink2: v("--ink-2", "#4f4a41"),
    ink3: v("--ink-3", "#6a6459"),
    pen: v("--pen", "#b8321a"),
    known: v("--known", "#2c5a86"),
    grid: v("--grid", "rgba(28,26,22,.07)"),
    gridStrong: v("--grid-strong", "rgba(28,26,22,.15)"),
    wash: v("--pen-wash", "rgba(184,50,26,.08)"),
    mono: v("--mono", "monospace"),
  };
}

export const outcomeColour = (ink: Ink, o: DetectionOutcome) => (o === "candidate" ? ink.pen : o === "known" ? ink.known : ink.ink3);

/** Where things sit on the canvas, in CSS pixels. */
export type Geom = {
  w: number;
  h: number;
  /** The margin lane (annotations) runs from 0 to laneH. */
  laneH: number;
  /** The trace band. */
  bandTop: number;
  bandBottom: number;
  /** Tape x (days) to screen x. */
  sx: (x: number) => number;
  /** Visible tape range. */
  x0: number;
  x1: number;
  pxPerDay: number;
};

export function makeGeom(w: number, h: number, pxPerDay: number, originPx: number, originX: number, compact: boolean): Geom {
  const laneH = compact ? 72 : 112;
  const bandTop = laneH + (compact ? 12 : 20);
  const bandBottom = h - (compact ? 34 : 40);
  const sx = (x: number) => originPx + (x - originX) * pxPerDay;
  return { w, h, laneH, bandTop, bandBottom, sx, pxPerDay, x0: originX - originPx / pxPerDay, x1: originX + (w - originPx) / pxPerDay };
}

const fy = (g: Geom, tape: Pick<Tape, "yTop" | "yBottom">, f: number) => g.bandTop + ((tape.yTop - f) / (tape.yTop - tape.yBottom)) * (g.bandBottom - g.bandTop);

/** The paper: ECG divisions, minor every day of tape and major every 5, moving with the data. */
export function drawPaper(ctx: CanvasRenderingContext2D, g: Geom, ink: Ink) {
  ctx.fillStyle = ink.paper;
  ctx.fillRect(0, 0, g.w, g.h);
  const minorPx = g.pxPerDay;
  const step = minorPx < 14 ? (minorPx < 4 ? 10 : 5) : 1;
  ctx.lineWidth = 1;
  const first = Math.floor(g.x0 / step) * step;
  for (let x = first; x <= g.x1; x += step) {
    const px = Math.round(g.sx(x)) + 0.5;
    const major = Math.round(x) % (step * 5) === 0;
    ctx.strokeStyle = major ? ink.gridStrong : ink.grid;
    ctx.beginPath();
    ctx.moveTo(px, g.laneH);
    ctx.lineTo(px, g.bandBottom);
    ctx.stroke();
  }
  // horizontal divisions: 8 across the band
  for (let k = 0; k <= 8; k++) {
    const py = Math.round(g.bandTop + ((g.bandBottom - g.bandTop) * k) / 8) + 0.5;
    ctx.strokeStyle = k === 0 || k === 8 ? ink.gridStrong : ink.grid;
    ctx.beginPath();
    ctx.moveTo(0, py);
    ctx.lineTo(g.w, py);
    ctx.stroke();
  }
  // the lane's base rule
  ctx.strokeStyle = ink.gridStrong;
  ctx.beginPath();
  ctx.moveTo(0, g.laneH + 0.5);
  ctx.lineTo(g.w, g.laneH + 0.5);
  ctx.stroke();
}

function label(ctx: CanvasRenderingContext2D, ink: Ink, text: string, x: number, y: number, colour: string, align: CanvasTextAlign = "left", size = 10.5, knockout = false) {
  ctx.font = `${size}px ${ink.mono}`;
  if (knockout) {
    const w = ctx.measureText(text).width;
    const x0 = align === "right" ? x - w : align === "center" ? x - w / 2 : x;
    ctx.fillStyle = ink.paper;
    ctx.fillRect(x0 - 3, y - size, w + 6, size + 4);
  }
  ctx.fillStyle = colour;
  ctx.textAlign = align;
  ctx.textBaseline = "alphabetic";
  ctx.fillText(text, x, y);
}

/** Dates under the major divisions and the sector number in each break, as a recorder prints its scale. */
export function drawScale(ctx: CanvasRenderingContext2D, g: Geom, ink: Ink, tape: Tape, upTo: number) {
  const y = g.bandBottom + 18;
  let lastPx = -Infinity;
  for (const s of tape.segments) {
    if (s.x0 > upTo) break;
    const firstDay = Math.ceil(s.t0);
    for (let tt = firstDay; tt <= s.t1; tt++) {
      const x = s.x0 + (tt - s.t0);
      if (x > upTo || x < g.x0 - 1 || x > g.x1 + 1) continue;
      const px = g.sx(x);
      if (px - lastPx < 64) continue;
      if (Math.round(tt) % (g.pxPerDay < 30 ? 10 : 5) !== 0 && px - lastPx < 120) continue;
      label(ctx, ink, fmtDay(btjdToMs(tt)).toUpperCase(), px + 3, y, ink.ink3);
      lastPx = px;
    }
    // the sector's name where its data begins
    if (s.sector != null) {
      const px = g.sx(s.x0);
      const prev = tape.segments[tape.segments.indexOf(s) - 1];
      const newSector = !prev || prev.sector !== s.sector;
      if (newSector && px > -80 && px < g.w) label(ctx, ink, `SECTOR ${s.sector}`, px + 4, g.bandTop + 15, ink.ink3, "left", 10.5, true);
    }
  }
}

/** A jump in the data longer than this (days) lifts the pen: about three missing 10-minute bins. */
const BREAK_D = 0.03;

export type MarkState = { mark: Mark; age: number };

/**
 * The margin lane: a tick for every dip reached, a rule down to the trace, and for the first dip of each
 * signal, its outcome and numbers. `alpha` fades each mark in over its first 160 ms.
 */
export function drawMarks(ctx: CanvasRenderingContext2D, g: Geom, ink: Ink, tape: Tape, dets: Detection[], marks: MarkState[], traceY: (x: number) => number | null, compact: boolean) {
  const rows = Math.max(1, Math.min(3, dets.length));
  const rowH = (g.laneH - 16) / rows;
  const visible = marks.filter(({ mark }) => {
    const px = g.sx(mark.x);
    return px > -220 && px < g.w + 20;
  });
  const ty = g.laneH;
  // pass 1: washes, ticks and rules
  for (const { mark, age } of visible) {
    const d = dets[mark.det];
    const px = g.sx(mark.x);
    const col = outcomeColour(ink, d.outcome);
    const rejected = d.outcome === "rejected";
    ctx.globalAlpha = Math.min(1, age / 0.16);

    // the dip's span, washed across the band (only for dips worth a second look)
    if (!rejected) {
      const x0 = g.sx(mark.x - mark.halfWidth);
      const x1 = g.sx(mark.x + mark.halfWidth);
      ctx.fillStyle = ink.wash;
      ctx.fillRect(x0, g.bandTop, Math.max(1.5, x1 - x0), g.bandBottom - g.bandTop);
    }

    // the tick at the lane's foot
    const size = mark.first ? 6 : 4;
    ctx.beginPath();
    ctx.moveTo(px - size, ty - size * 1.5);
    ctx.lineTo(px + size, ty - size * 1.5);
    ctx.lineTo(px, ty);
    ctx.closePath();
    if (rejected) {
      ctx.strokeStyle = col;
      ctx.lineWidth = 1;
      ctx.stroke();
    } else {
      ctx.fillStyle = col;
      ctx.fill();
      if (d.outcome === "known") ctx.fillRect(px - size, ty - size * 1.5 - 3, size * 2, 1.5);
    }

    // the rule down to the line: every dip worth a look, and the first dip of a rejected signal
    if (!rejected || mark.first) {
      const yTrace = traceY(mark.x);
      ctx.strokeStyle = col;
      ctx.lineWidth = 1;
      ctx.setLineDash(rejected ? [2, 3] : []);
      ctx.beginPath();
      ctx.moveTo(Math.round(px) + 0.5, ty + 2);
      ctx.lineTo(Math.round(px) + 0.5, yTrace != null ? yTrace - 6 : g.bandTop);
      ctx.stroke();
      ctx.setLineDash([]);
    }
    if (mark.first) {
      const base = 14 + (mark.det % rows) * rowH;
      ctx.strokeStyle = col;
      ctx.beginPath();
      ctx.moveTo(Math.round(px) + 0.5, base - 9);
      ctx.lineTo(Math.round(px) + 0.5, ty - size * 1.5);
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }
  // pass 2: the notes, over everything, knocked out of the paper
  for (const { mark, age } of visible) {
    if (!mark.first) continue;
    const d = dets[mark.det];
    const px = g.sx(mark.x);
    const col = outcomeColour(ink, d.outcome);
    ctx.globalAlpha = Math.min(1, age / 0.16);
    const base = 14 + (mark.det % rows) * rowH;
    const word = d.outcome === "candidate" ? "CANDIDATE" : d.outcome === "known" ? "KNOWN" : "REJECTED";
    const right = px + 210 > g.w;
    const lx = right ? px - 7 : px + 7;
    const size = compact ? 10 : 11;
    label(ctx, ink, word, lx, base, col, right ? "right" : "left", size, true);
    if (rowH > 22) label(ctx, ink, detectionLabel(d), lx, base + 14, ink.ink2, right ? "right" : "left", size, true);
    ctx.globalAlpha = 1;
  }
}

/**
 * The trace: one ink line from tape x `from` to `to`, broken at every gap. Dips already marked are
 * redrawn in their outcome's colour (candidate and known; rejected dips stay ink).
 */
export function drawTrace(ctx: CanvasRenderingContext2D, g: Geom, ink: Ink, tape: Tape, from: number, to: number, lit: MarkState[], dets: Detection[], width: number) {
  const n = tape.x.length;
  if (!n || to <= from) return;
  const i0 = Math.max(0, lowerBound(tape.x, Math.max(from, g.x0 - 0.2)) - 1);
  const i1 = Math.min(n, lowerBound(tape.x, Math.min(to, g.x1 + 0.2)) + 1);
  ctx.lineJoin = "round";
  ctx.lineCap = "round";
  const path = (a: number, b: number) => {
    ctx.beginPath();
    let pen = false;
    for (let i = a; i < b; i++) {
      if (tape.x[i] > to) break;
      const px = g.sx(tape.x[i]);
      const py = fy(g, tape, tape.f[i]);
      if (!pen || (i > 0 && tape.x[i] - tape.x[i - 1] > BREAK_D)) ctx.moveTo(px, py);
      else ctx.lineTo(px, py);
      pen = true;
    }
    ctx.stroke();
  };
  ctx.strokeStyle = ink.ink;
  ctx.lineWidth = width;
  path(i0, i1);
  for (const { mark } of lit) {
    const d = dets[mark.det];
    if (d.outcome === "rejected") continue;
    const a = lowerBound(tape.x, mark.x - mark.halfWidth * 1.2);
    const b = lowerBound(tape.x, Math.min(to, mark.x + mark.halfWidth * 1.2));
    if (b <= a) continue;
    ctx.strokeStyle = outcomeColour(ink, d.outcome);
    ctx.lineWidth = width + 0.75;
    path(Math.max(0, a - 1), Math.min(n, b + 1));
  }
}

/** The pen: a small ink dot where the line is being written, and the stylus rule across the band. */
export function drawPen(ctx: CanvasRenderingContext2D, g: Geom, ink: Ink, tape: Tape, x: number) {
  const i = Math.min(tape.x.length - 1, Math.max(0, lowerBound(tape.x, x) - 1));
  const px = g.sx(x);
  ctx.strokeStyle = ink.gridStrong;
  ctx.lineWidth = 1;
  ctx.beginPath();
  ctx.moveTo(Math.round(px) + 0.5, g.laneH);
  ctx.lineTo(Math.round(px) + 0.5, g.bandBottom);
  ctx.stroke();
  if (i < 0 || !tape.x.length) return;
  const py = fy(g, tape, tape.f[i]);
  ctx.fillStyle = ink.ink;
  ctx.beginPath();
  ctx.arc(px, py, 3, 0, Math.PI * 2);
  ctx.fill();
}

/** The trace's height at tape x, for rules and the cursor. */
export function traceYAt(g: Geom, tape: Tape, x: number): number | null {
  const i = lowerBound(tape.x, x);
  if (i >= tape.x.length || Math.abs(tape.x[i] - x) > 0.3) return null;
  return fy(g, tape, tape.f[i]);
}

/** The flux scale on the band's right edge: where 1.000 sits, and the band's floor in ppm. */
export function drawFluxScale(ctx: CanvasRenderingContext2D, g: Geom, ink: Ink, tape: Tape) {
  const x = g.w - 6;
  const y1 = fy(g, tape, 1);
  if (y1 > g.bandTop + 14 && y1 < g.bandBottom - 18) label(ctx, ink, "1.000", x, y1 - 5, ink.ink3, "right", 10.5, true);
  const floor = Math.round((tape.yBottom - 1) * 1e6);
  const text = `${floor < 0 ? "\u2212" : "+"}${Math.abs(floor).toLocaleString("en-GB").replace(/,/g, "\u2009")} PPM`;
  label(ctx, ink, text, x, g.bandBottom - 6, ink.ink3, "right", 10.5, true);
}

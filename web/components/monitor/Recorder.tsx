"use client";

import { useEffect, useMemo, useRef } from "react";
import type { MonitorStar } from "@/lib/api";
import { drawCursor, drawFluxScale, drawMarks, drawPaper, drawPen, drawScale, drawTrace, makeGeom, readInk, traceYAt, type MarkState } from "./draw";
import { ADVANCE_S, buildTape, drawSeconds, easeInOut, PEN_AT, penAt, phaseAt, type Tape } from "./trace";
import s from "./monitor.module.css";

/** The whole light curve, drawn still and fitted to the width, with every dip marked. */
export function StillTrace({ star, label }: { star: MonitorStar; label: string }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const tape = useMemo(() => buildTape(star), [star]);
  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const paint = () => {
      const { width: w, height: h } = canvas.getBoundingClientRect();
      if (!w || !h) return;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const ink = readInk(canvas);
      const compact = w < 720;
      const pad = compact ? 12 : 32;
      const pxPerDay = (w - 2 * pad) / Math.max(tape.length, 1);
      const g = makeGeom(w, h, pxPerDay, pad, 0, compact);
      drawPaper(ctx, g, ink);
      const marks: MarkState[] = tape.marks.map((mark) => ({ mark, age: 1 }));
      drawMarks(ctx, g, ink, tape, star.detections, marks, (x) => traceYAt(g, tape, x), compact);
      drawTrace(ctx, g, ink, tape, 0, tape.length, marks, star.detections, compact ? 1.25 : 1.5);
      drawScale(ctx, g, ink, tape, tape.length);
      drawFluxScale(ctx, g, ink, tape);
    };
    paint();
    const ro = new ResizeObserver(paint);
    ro.observe(canvas);
    const mq = matchMedia("(prefers-color-scheme: dark)");
    mq.addEventListener("change", paint);
    return () => {
      ro.disconnect();
      mq.removeEventListener("change", paint);
    };
  }, [tape, star.detections]);
  return <canvas ref={ref} className={s.canvas} role="img" aria-label={label} />;
}

// ---------- the streaming recorder (DESIGN.md: The monitor) ----------

/** Pixels per day of tape: about 13 days across a desktop, 7 on a phone. */
const pxPerDayFor = (w: number) => Math.max(40, Math.min(120, w / 13));
/** A skip the viewer asked for (button or →) advances fast; the recorder's own handover takes its time. */
const SKIP_ADVANCE_S = 0.24;

type Run = {
  star: MonitorStar;
  tape: Tape;
  /** Seconds of drawing so far (only counts while playing and visible). */
  elapsed: number;
  /** When each mark was reached, in `elapsed` seconds. */
  reached: number[];
  /** Paper already moved before this star, in days, so the grid runs on. */
  phase: number;
  finished: boolean;
  /** Whether the parent has been told this star is on the paper. */
  started: boolean;
};

type Leaving = { run: Run; t: number; dur: number };

export function StreamTrace({
  star,
  paused,
  onFinished,
  onMark,
  onStart,
  label,
}: {
  star: MonitorStar;
  paused: boolean;
  /** Called when a star starts drawing (after the paper has advanced), so the page names the star on the paper. */
  onStart: (star: MonitorStar) => void;
  /** Called once when the star has been drawn and has held; the parent then brings the next star. */
  onFinished: () => void;
  /** Called when the pen reaches the first dip of a detection. */
  onMark: (star: MonitorStar, det: number) => void;
  label: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const run = useRef<Run | null>(null);
  const leaving = useRef<Leaving | null>(null);
  const pausedRef = useRef(paused);
  const pointer = useRef<number | null>(null);
  const cb = useRef({ onFinished, onMark, onStart });
  const dirty = useRef(true);

  useEffect(() => {
    cb.current = { onFinished, onMark, onStart };
  }, [onFinished, onMark, onStart]);

  useEffect(() => {
    pausedRef.current = paused;
    dirty.current = true;
  }, [paused]);

  // A new star: the old one slides off with the paper; fast if the viewer skipped, slow at a natural end.
  useEffect(() => {
    const prev = run.current;
    const tape = buildTape(star);
    let phase = 0;
    if (prev) {
      const skipped = !prev.finished;
      const x = Math.min(prev.elapsed >= drawSeconds(prev.tape.length) ? prev.tape.length : penAt(prev.elapsed, prev.tape.length), prev.tape.length);
      leaving.current = { run: { ...prev, tape: { ...prev.tape, length: x } }, t: 0, dur: skipped ? SKIP_ADVANCE_S : ADVANCE_S };
      phase = prev.phase + x;
    }
    run.current = { star, tape, elapsed: 0, reached: tape.marks.map(() => -1), phase, finished: false, started: false };
    dirty.current = true;
  }, [star]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    let ink = readInk(canvas);
    let raf = 0;
    let last = 0;
    let onScreen = true;
    let w = 0;
    let h = 0;
    let dpr = 1;

    const size = () => {
      const r = canvas.getBoundingClientRect();
      w = r.width;
      h = r.height;
      dpr = Math.min(2, window.devicePixelRatio || 1);
      canvas.width = Math.round(w * dpr);
      canvas.height = Math.round(h * dpr);
      dirty.current = true;
    };

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = last ? Math.min((now - last) / 1000, 0.05) : 0; // a stalled frame never jumps the pen
      last = now;
      const r = run.current;
      const ctx = canvas.getContext("2d");
      if (!r || !ctx || !w || !h) return;
      const moving = !pausedRef.current;
      if (!moving && !dirty.current) return;
      dirty.current = false;

      const L = r.tape.length;
      const leave = leaving.current;
      if (leave && moving) leave.t += dt;
      const advancing = leave && leave.t < leave.dur;
      if (leave && !advancing) leaving.current = null;
      if (moving && !advancing) r.elapsed += dt;
      if (!advancing && !r.started) {
        r.started = true;
        cb.current.onStart(r.star);
      }

      const compact = w < 720;
      const ppd = pxPerDayFor(w);
      const penPx = Math.round(w * PEN_AT);
      const ph = phaseAt(r.elapsed, L);
      const penX = ph.kind === "drawing" ? ph.x : L;

      // marks the pen has passed
      r.tape.marks.forEach((m, k) => {
        if (r.reached[k] < 0 && m.x <= penX) {
          r.reached[k] = r.elapsed;
          if (m.first) cb.current.onMark(r.star, m.det);
        }
      });
      if (!r.finished && (ph.kind === "advancing" || ph.kind === "done")) {
        r.finished = true;
        cb.current.onFinished();
      }

      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

      if (advancing && leave) {
        // the paper advances: the finished trace slides left and blank paper comes under the pen
        const p = easeInOut(leave.t / leave.dur);
        const o = leave.run;
        const shift = p * penPx;
        const g = makeGeom(w, h, ppd, penPx - shift, o.tape.length, compact);
        drawPaper(ctx, g, ink, o.phase);
        const marks = o.tape.marks.flatMap((mark, k) => (o.reached[k] >= 0 ? [{ mark, age: 1 }] : []));
        drawMarks(ctx, g, ink, o.tape, o.star.detections, marks, (x) => traceYAt(g, o.tape, x), compact);
        drawTrace(ctx, g, ink, o.tape, 0, o.tape.length, marks, o.star.detections, compact ? 1.25 : 1.5);
        drawScale(ctx, g, ink, o.tape, o.tape.length);
        return;
      }

      const g = makeGeom(w, h, ppd, penPx, penX, compact);
      drawPaper(ctx, g, ink, r.phase);
      const marks: MarkState[] = r.tape.marks.flatMap((mark, k) => (r.reached[k] >= 0 ? [{ mark, age: r.elapsed - r.reached[k] }] : []));
      drawMarks(ctx, g, ink, r.tape, r.star.detections, marks, (x) => traceYAt(g, r.tape, x), compact);
      drawTrace(ctx, g, ink, r.tape, 0, penX, marks, r.star.detections, compact ? 1.25 : 1.5);
      drawScale(ctx, g, ink, r.tape, penX);
      drawFluxScale(ctx, g, ink, r.tape);
      if (ph.kind === "drawing") drawPen(ctx, g, ink, r.tape, penX);
      const px = pointer.current;
      if (px != null) {
        const x = penX - (penPx - px) / ppd;
        if (x >= 0 && x <= penX) drawCursor(ctx, g, ink, r.tape, x);
      }
      // keep fading marks and the moving pen repainting
      if (marks.some((m) => m.age < 0.2)) dirty.current = true;
    };

    const start = () => {
      if (raf || document.hidden || !onScreen) return;
      last = 0;
      dirty.current = true;
      raf = requestAnimationFrame(frame);
    };
    const stop = () => {
      cancelAnimationFrame(raf);
      raf = 0;
    };

    size();
    start();
    const ro = new ResizeObserver(size);
    ro.observe(canvas);
    // pause when the tab is hidden or the monitor is scrolled away; resume where it was
    const vis = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", vis);
    const io = new IntersectionObserver(([e]) => {
      onScreen = e.isIntersecting;
      if (onScreen) start();
      else stop();
    });
    io.observe(canvas);
    const mq = matchMedia("(prefers-color-scheme: dark)");
    const theme = () => {
      ink = readInk(canvas);
      dirty.current = true;
    };
    mq.addEventListener("change", theme);
    return () => {
      stop();
      ro.disconnect();
      io.disconnect();
      document.removeEventListener("visibilitychange", vis);
      mq.removeEventListener("change", theme);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={s.canvas}
      role="img"
      aria-label={label}
      onPointerMove={(e) => {
        if (e.pointerType !== "mouse") return;
        pointer.current = e.nativeEvent.offsetX;
        dirty.current = true;
      }}
      onPointerLeave={() => {
        pointer.current = null;
        dirty.current = true;
      }}
    />
  );
}

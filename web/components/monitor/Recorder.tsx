"use client";

import { useEffect, useMemo, useRef } from "react";
import type { MonitorStar } from "@/lib/api";
import { drawFluxScale, drawMarks, drawPaper, drawScale, drawTrace, makeGeom, readInk, traceYAt, type MarkState } from "./draw";
import { buildTape } from "./trace";
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

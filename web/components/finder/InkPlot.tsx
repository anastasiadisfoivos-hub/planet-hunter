"use client";

import { useEffect, useRef } from "react";
import { readInk } from "@/components/monitor/draw";
import s from "./finder.module.css";

export type Series = { x: number[]; y: number[]; style: "dots" | "line"; colour: "ink" | "pen" | "ink3" };

/**
 * A small chart on recorder paper: divisions, mono scale labels on the edges, and series drawn with the
 * monitor's ink. Used for the dossier's folded and unfolded curves.
 */
export function InkPlot({
  series,
  xRange,
  yRange,
  xTicks,
  xLabel,
  yLabel,
  label,
  height = 260,
  marks = [],
}: {
  series: Series[];
  xRange: [number, number];
  yRange: [number, number];
  xTicks: { at: number; text: string }[];
  xLabel: string;
  yLabel: string;
  label: string;
  height?: number;
  /** Vertical marks (e.g. each transit), drawn as pen ticks at the top. */
  marks?: number[];
}) {
  const ref = useRef<HTMLCanvasElement>(null);
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
      const L = 8;
      const R = 8;
      const T = 14;
      const B = 30;
      const px = (x: number) => L + ((x - xRange[0]) / (xRange[1] - xRange[0])) * (w - L - R);
      const py = (y: number) => T + ((yRange[1] - y) / (yRange[1] - yRange[0])) * (h - T - B);
      ctx.fillStyle = ink.paper;
      ctx.fillRect(0, 0, w, h);
      ctx.lineWidth = 1;
      for (let k = 0; k <= 10; k++) {
        const x = Math.round(L + ((w - L - R) * k) / 10) + 0.5;
        ctx.strokeStyle = k % 5 === 0 ? ink.gridStrong : ink.grid;
        ctx.beginPath();
        ctx.moveTo(x, T);
        ctx.lineTo(x, h - B);
        ctx.stroke();
      }
      for (let k = 0; k <= 6; k++) {
        const y = Math.round(T + ((h - T - B) * k) / 6) + 0.5;
        ctx.strokeStyle = k % 3 === 0 ? ink.gridStrong : ink.grid;
        ctx.beginPath();
        ctx.moveTo(L, y);
        ctx.lineTo(w - R, y);
        ctx.stroke();
      }
      ctx.font = `10.5px ${ink.mono}`;
      ctx.fillStyle = ink.ink3;
      ctx.textBaseline = "alphabetic";
      for (const t of xTicks) {
        const x = px(t.at);
        if (x < L - 1 || x > w - R + 1) continue;
        ctx.textAlign = x > w - 60 ? "right" : x < 40 ? "left" : "center";
        ctx.fillText(t.text, x, h - B + 16);
      }
      ctx.textAlign = "right";
      ctx.fillText(xLabel.toUpperCase(), w - R, h - 4);
      ctx.textAlign = "left";
      ctx.fillText(yLabel.toUpperCase(), L + 4, T - 3);
      const col = { ink: ink.ink, pen: ink.pen, ink3: ink.ink3 };
      for (const m of marks) {
        const x = px(m);
        if (x < L || x > w - R) continue;
        ctx.fillStyle = ink.pen;
        ctx.beginPath();
        ctx.moveTo(x - 4, T);
        ctx.lineTo(x + 4, T);
        ctx.lineTo(x, T + 6);
        ctx.fill();
      }
      ctx.save();
      ctx.beginPath();
      ctx.rect(L, T, w - L - R, h - T - B);
      ctx.clip();
      for (const s of series) {
        ctx.fillStyle = col[s.colour];
        ctx.strokeStyle = col[s.colour];
        if (s.style === "dots") {
          const r = s.x.length > 3000 ? 0.9 : 1.3;
          for (let i = 0; i < s.x.length; i++) ctx.fillRect(px(s.x[i]) - r / 2, py(s.y[i]) - r / 2, r, r);
        } else {
          ctx.lineWidth = 2;
          ctx.lineJoin = "round";
          ctx.beginPath();
          s.x.forEach((x, i) => (i ? ctx.lineTo(px(x), py(s.y[i])) : ctx.moveTo(px(x), py(s.y[i]))));
          ctx.stroke();
        }
      }
      ctx.restore();
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
  }, [series, xRange, yRange, xTicks, xLabel, yLabel, marks]);
  return <canvas ref={ref} className={s.plot} style={{ height }} role="img" aria-label={label} />;
}

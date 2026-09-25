"use client";

import { useMemo } from "react";
import type { Candidate } from "@/lib/api";
import { linear, ticks } from "@/components/lab/chart";
import { useWidth } from "@/components/lab/hooks";
import { binFolded, transitTimes } from "./finder";
import s from "./finder.module.css";

const PAD = { l: 52, r: 12, t: 28, b: 40 };

/** Every point as a zero-length round-capped segment: one path element however many points. */
function dots(xs: number[], ys: number[], x: (v: number) => number, y: (v: number) => number, keep: (i: number) => boolean) {
  let d = "";
  for (let i = 0; i < xs.length; i++) if (keep(i)) d += `M${x(xs[i]).toFixed(1)} ${y(ys[i]).toFixed(1)}h0`;
  return d;
}

/** A robust flux range: the 0.3rd to 99.7th percentile of the points shown, padded. */
function fluxRange(fl: number[]): [number, number] {
  const s = [...fl].sort((a, b) => a - b);
  const lo = s[Math.floor(s.length * 0.003)];
  const hi = s[Math.floor(s.length * 0.997)];
  const pad = (hi - lo) * 0.08;
  return [lo - pad, hi + pad];
}

/** Change in brightness in percent, the same unit as the dip depth. */
const fmtFlux = (v: number) => {
  const pc = (v - 1) * 100;
  return Math.abs(pc) < 1e-9 ? "0" : `${pc.toFixed(Math.abs(pc) < 0.1 ? 3 : Math.abs(pc) < 1 ? 2 : 1).replace(/\.?0+$/, "")}%`;
};

export function FoldedCurve({ c }: { c: Candidate }) {
  const [ref, w] = useWidth<HTMLDivElement>(420);
  const h = 260;
  const half = Math.max(c.duration_h * 2.5, 3);
  const hours = useMemo(() => c.folded.phase.map((p) => p * c.period_d * 24), [c]);
  const view = useMemo(() => hours.map((hr) => hr >= -half && hr <= half), [hours, half]);
  const binned = useMemo(() => binFolded(hours, c.folded.flux, half, 48), [hours, c, half]);
  const [f0, f1] = useMemo(() => fluxRange(c.folded.flux.filter((_, i) => view[i])), [c, view]);
  const x = linear([-half, half], [PAD.l, w - PAD.r]);
  const y = linear([f0, f1], [h - PAD.b, PAD.t]);
  const xt = ticks(-half, half, w < 360 ? 4 : 6);
  const yt = ticks(f0, f1, 4);
  return (
    <div className={s.chartBox}>
      <div className={s.chartHead}>
        <h3 className={s.chartTitle}>Folded on the period</h3>
        <span className="label">{c.n_transits} dips stacked</span>
      </div>
      <div ref={ref}>
        <svg
          className={s.svg}
          width={w}
          height={h}
          role="img"
          aria-label={`All ${c.n_transits} dips stacked on the ${c.period_d.toFixed(4)}-day period. The dip is ${Math.round(c.depth_ppm)} parts per million deep and ${c.duration_h.toFixed(1)} hours long.`}
        >
          <rect className={s.durationBand} x={x(-c.duration_h / 2)} width={x(c.duration_h / 2) - x(-c.duration_h / 2)} y={PAD.t} height={h - PAD.t - PAD.b} />
          {yt.map((v) => (
            <g key={v}>
              <line className={s.gridLine} x1={PAD.l} x2={w - PAD.r} y1={y(v)} y2={y(v)} />
              <text className={s.axis} x={PAD.l - 8} y={y(v) + 4} textAnchor="end">
                {fmtFlux(v)}
              </text>
            </g>
          ))}
          <text className={s.axisTitle} x={PAD.l - 8} y={PAD.t - 12}>
            Change in brightness
          </text>
          <path className={s.points} strokeWidth={2} d={dots(hours, c.folded.flux, x, y, (i) => view[i])} opacity={0.55} />
          <path className={s.binned} d={binned.map((p, i) => `${i ? "L" : "M"}${x(p.x).toFixed(1)} ${y(p.y).toFixed(1)}`).join("")} />
          <line className={s.gridLine} x1={PAD.l} x2={w - PAD.r} y1={h - PAD.b} y2={h - PAD.b} />
          {xt.map((v) => (
            <text key={v} className={s.axis} x={x(v)} y={h - PAD.b + 16} textAnchor="middle">
              {v > 0 ? `+${v}` : v}
            </text>
          ))}
          <text className={s.axisTitle} x={w - PAD.r} y={h - 6} textAnchor="end">
            Hours from mid-dip
          </text>
        </svg>
      </div>
      <ul className={s.legend}>
        <li>
          <span className={s.keyDot} aria-hidden />
          30-minute points
        </li>
        <li>
          <span className={s.keyLine} aria-hidden />
          Median
        </li>
        <li>
          <span className={s.keyDot} style={{ borderRadius: 2, background: "var(--accent-tint)", width: 12, height: 10 }} aria-hidden />
          Dip duration
        </li>
      </ul>
    </div>
  );
}

export function UnfoldedCurve({ c }: { c: Candidate }) {
  const [ref, w] = useWidth<HTMLDivElement>(640);
  const h = 260;
  const t = c.unfolded.time_btjd;
  const [t0, t1] = [t[0], t[t.length - 1]];
  const [f0, f1] = useMemo(() => fluxRange(c.unfolded.flux), [c]);
  const x = linear([t0, t1], [PAD.l, w - PAD.r]);
  const y = linear([f0, f1], [h - PAD.b, PAD.t]);
  const marks = transitTimes(c.t0_btjd, c.period_d, t0, t1);
  const xt = ticks(t0, t1, w < 420 ? 3 : 6);
  const yt = ticks(f0, f1, 4);
  const d = useMemo(() => dots(t, c.unfolded.flux, x, y, () => true), [t, c, x, y]);
  return (
    <div className={s.chartBox}>
      <div className={s.chartHead}>
        <h3 className={s.chartTitle}>The whole light curve</h3>
        <span className="label">
          TESS sector{c.sectors.length > 1 ? "s" : ""} {c.sectors.join(", ")}
        </span>
      </div>
      <div ref={ref}>
        <svg
          className={s.svg}
          width={w}
          height={h}
          role="img"
          aria-label={`Brightness over ${Math.round(t1 - t0)} days of TESS data with the ${marks.length} predicted dip times marked.`}
        >
          {yt.map((v) => (
            <g key={v}>
              <line className={s.gridLine} x1={PAD.l} x2={w - PAD.r} y1={y(v)} y2={y(v)} />
              <text className={s.axis} x={PAD.l - 8} y={y(v) + 4} textAnchor="end">
                {fmtFlux(v)}
              </text>
            </g>
          ))}
          <text className={s.axisTitle} x={PAD.l - 8} y={PAD.t - 12}>
            Change in brightness
          </text>
          {marks.map((m) => (
            <line key={m} className={s.transitMark} x1={x(m)} x2={x(m)} y1={PAD.t - 2} y2={PAD.t + 8} />
          ))}
          <path className={s.points} strokeWidth={1.6} d={d} opacity={0.7} />
          <line className={s.gridLine} x1={PAD.l} x2={w - PAD.r} y1={h - PAD.b} y2={h - PAD.b} />
          {xt.map((v) => (
            <text key={v} className={s.axis} x={x(v)} y={h - PAD.b + 16} textAnchor="middle">
              {v}
            </text>
          ))}
          <text className={s.axisTitle} x={w - PAD.r} y={h - 6} textAnchor="end">
            Days (BTJD)
          </text>
        </svg>
      </div>
      <ul className={s.legend}>
        <li>
          <span className={s.keyTick} aria-hidden />
          Predicted dip
        </li>
        <li>Gaps are when TESS sent its data home.</li>
      </ul>
    </div>
  );
}

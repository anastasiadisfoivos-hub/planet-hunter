// Tiny chart helpers: linear/log scales, tick values and plain SVG axes. No chart library.

import type { ReactNode } from "react";
import { Button } from "@/components/ui";
import s from "./lab.module.css";

export type Scale = ((v: number) => number) & { invert: (px: number) => number; domain: [number, number]; range: [number, number] };

export function linear(domain: [number, number], range: [number, number]): Scale {
  const [d0, d1] = domain;
  const [r0, r1] = range;
  const f = ((v: number) => r0 + ((v - d0) / (d1 - d0)) * (r1 - r0)) as Scale;
  f.invert = (px) => d0 + ((px - r0) / (r1 - r0)) * (d1 - d0);
  f.domain = domain;
  f.range = range;
  return f;
}

export function log(domain: [number, number], range: [number, number]): Scale {
  const l = linear([Math.log10(domain[0]), Math.log10(domain[1])], range);
  const f = ((v: number) => l(Math.log10(v))) as Scale;
  f.invert = (px) => 10 ** l.invert(px);
  f.domain = domain;
  f.range = range;
  return f;
}

/** Round tick values: about `count` of them across the domain. */
export function ticks(d0: number, d1: number, count = 5): number[] {
  const lo = Math.min(d0, d1);
  const hi = Math.max(d0, d1);
  const raw = (hi - lo) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((st) => st >= raw) ?? raw;
  const out: number[] = [];
  for (let v = Math.ceil(lo / step) * step; v <= hi + step * 1e-9; v += step) out.push(Number(v.toPrecision(12)));
  return out;
}

export const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

/** Bottom axis with tick labels and an uppercase mono title. */
export function XAxis({ x, y, values, format, title, grid }: { x: Scale; y: number; values: number[]; format: (v: number) => string; title?: string; grid?: [number, number] }) {
  const [a, b] = x.range;
  return (
    <g aria-hidden>
      {grid && values.map((v) => <line key={`g${v}`} className={s.gridLine} x1={x(v)} x2={x(v)} y1={grid[0]} y2={grid[1]} />)}
      <line className={s.gridLine} x1={a} x2={b} y1={y} y2={y} />
      {values.map((v) => (
        <text key={v} className={s.axis} x={x(v)} y={y + 16} textAnchor="middle">
          {format(v)}
        </text>
      ))}
      {title && (
        <text className={s.axisTitle} x={b} y={y + 34} textAnchor="end">
          {title}
        </text>
      )}
    </g>
  );
}

/** Left axis with tick labels; the title sits above the axis, left-aligned, so it never rotates. */
export function YAxis({ y, x, values, format, title, grid }: { y: Scale; x: number; values: number[]; format: (v: number) => string; title?: string; grid?: [number, number] }) {
  return (
    <g aria-hidden>
      {grid && values.map((v) => <line key={`g${v}`} className={s.gridLine} x1={grid[0]} x2={grid[1]} y1={y(v)} y2={y(v)} />)}
      {values.map((v) => (
        <text key={v} className={s.axis} x={x - 8} y={y(v) + 4} textAnchor="end">
          {format(v)}
        </text>
      ))}
      {title && (
        <text className={s.axisTitle} x={x - 8} y={Math.min(...y.range) - 12} textAnchor="start">
          {title}
        </text>
      )}
    </g>
  );
}

export function Skeleton({ label }: { label: string }) {
  return (
    <div className={s.skeleton} aria-busy="true" role="status">
      <span className="sr-only">{label}</span>
    </div>
  );
}

export function LoadError({ what, error, onRetry }: { what: string; error: string; onRetry: () => void }) {
  return (
    <div className={s.error} role="alert">
      <p className={s.h3}>{what} didn&apos;t load</p>
      <p className={s.help}>{error}</p>
      <Button variant="primary" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

export function Note({ icon, children }: { icon: ReactNode; children: ReactNode }) {
  return (
    <p className={s.note}>
      {icon}
      <span>{children}</span>
    </p>
  );
}

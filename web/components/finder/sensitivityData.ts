// hunt's sensitivity file as the page's grid. No React and no "@/" value imports, so node --test can load it.

import type { Sensitivity } from "../../lib/api.ts";

/** hunt's own sensitivity file (hunt/results/sensitivity.json), which the API stores as given. */
export type HuntSensitivity = {
  created_at: string;
  n_stars: number;
  grid: { radius_edges_rearth: number[]; period_edges_d: number[] };
  bins: { radius_rearth: [number, number]; period_d: [number, number]; n_injected: number; recovery_fraction: number }[];
  definition?: Record<string, string>;
  overall_recovery_fraction?: number;
};

/** The grid the page draws, from hunt's file (as the mock's builder does) or already in that shape. */
export function toSensitivity(s: Sensitivity | HuntSensitivity): Sensitivity {
  if (!("bins" in s)) return s;
  const re = s.grid.radius_edges_rearth;
  const pe = s.grid.period_edges_d;
  const cell = new Map(s.bins.map((b) => [`${b.radius_rearth.join()}|${b.period_d.join()}`, b]));
  const grid = re.slice(0, -1).map((_, i) => pe.slice(0, -1).map((_, j) => cell.get(`${re[i]},${re[i + 1]}|${pe[j]},${pe[j + 1]}`)));
  const pct = (f: number) => Math.round(f * 1000) / 10;
  return {
    run_at: s.created_at.replace("+00:00", "Z"),
    stars_used: s.n_stars,
    radius_edges_rearth: re,
    period_edges_d: pe,
    recovery_pct: grid.map((row) => row.map((c) => (c ? pct(c.recovery_fraction) : null))),
    n_injected: grid.map((row) => row.map((c) => c?.n_injected ?? 0)),
    definition: s.definition,
    overall_recovery_pct: s.overall_recovery_fraction != null ? pct(s.overall_recovery_fraction) : undefined,
  };
}

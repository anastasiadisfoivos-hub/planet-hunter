"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getSensitivity, type Sensitivity } from "@/lib/api";
import { fmtDate, thousands } from "@/components/monitor/format";
import s from "./sensitivity.module.css";

const range = (a: number, b: number, unit: string) => `${a} to ${b}${unit}`;

/** The injection-recovery grid: how often the search finds a planet of each size and period. */
export function SensitivityGrid() {
  const [data, setData] = useState<Sensitivity | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    const ac = new AbortController();
    getSensitivity(ac.signal)
      .then((r) => setData(r.data))
      .catch(() => !ac.signal.aborted && setError(true));
    return () => ac.abort();
  }, []);

  const rows = data ? data.radius_edges_rearth.slice(0, -1).map((_, i) => i).reverse() : [];
  const cols = data ? data.period_edges_d.slice(0, -1).map((_, j) => j) : [];
  const injected = data ? data.n_injected.flat().reduce((a, b) => a + b, 0) : 0;
  return (
    <div className={`wrap ${s.page}`}>
      <header className={s.head}>
        <h1>What the search can find</h1>
        <div className="prose">
          <p>
            We hid fake planets in the real light curves of quiet stars and ran the search again. Each square says how often it found them
            and would have kept them as candidates.
          </p>
          {data && (
            <p className="label">
              {`${thousands(injected)} planets hidden in ${thousands(data.stars_used)} stars · run ${fmtDate(data.run_at)}`}
              {data.overall_recovery_pct != null ? ` · ${data.overall_recovery_pct}% kept overall` : ""}
            </p>
          )}
        </div>
      </header>
      {error && <p className="italic quiet">The sensitivity run could not be loaded.</p>}
      {!data && !error && <div className={s.wait} role="status" aria-label="Loading" />}
      {data && (
        <div className={s.scroll}>
          <table className={s.grid}>
            <caption className="sr-only">Share of hidden planets the search kept, by size (rows) and orbital period (columns)</caption>
            <thead>
              <tr>
                <th scope="col" className="label">
                  Size \ period
                </th>
                {cols.map((j) => (
                  <th key={j} scope="col" className="label">
                    {range(data.period_edges_d[j], data.period_edges_d[j + 1], " d")}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((i) => (
                <tr key={i}>
                  <th scope="row" className="label">
                    {range(data.radius_edges_rearth[i], data.radius_edges_rearth[i + 1], " × Earth")}
                  </th>
                  {cols.map((j) => {
                    const p = data.recovery_pct[i][j];
                    const n = data.n_injected[i][j];
                    return (
                      <td key={j} className={s.cell} style={{ ["--p" as string]: p == null ? 0 : p / 100 }} data-dark={p != null && p >= 55 ? "" : undefined}>
                        <span className={s.pct}>{p == null ? "–" : `${Math.round(p)}%`}</span>
                        <span className={s.n}>{n ? `of ${n}` : "none tried"}</span>
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data?.definition && (
        <dl className={s.defs}>
          {Object.entries(data.definition).map(([k, v]) => (
            <div key={k}>
              <dt className="label">{k.replace(/_/g, " ")}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      )}
      <p className={s.after}>
        <Link href="/methods">How the search works</Link>
      </p>
    </div>
  );
}

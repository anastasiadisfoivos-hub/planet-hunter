"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { DemoTag } from "@/components/ui";
import { LoadError, nf0 } from "@/components/lab/chart";
import { getCandidates, getSensitivity, type CandidateRow, type Sensitivity as Grid, type Served } from "@/lib/api";
import { fmtPeriod, rEarth } from "./finder";
import { formatUtc } from "@/lib/format";
import s from "./finder.module.css";
import l from "@/components/lab/lab.module.css";

/** Position of v across bins with these edges, 0 to 1, log-interpolated inside a bin. Null when outside. */
export function binPos(edges: number[], v: number): number | null {
  if (v < edges[0] || v > edges[edges.length - 1]) return null;
  const n = edges.length - 1;
  for (let i = 0; i < n; i++) {
    if (v <= edges[i + 1]) return (i + Math.log(v / edges[i]) / Math.log(edges[i + 1] / edges[i])) / n;
  }
  return 1;
}

const fmtEdge = (v: number) => (Number.isInteger(v) ? nf0.format(v) : v.toString());
const cellFill = (p: number) => `color-mix(in oklab, var(--ink) ${Math.round((p / 100) * 88)}%, var(--bg-deep))`;

export function Sensitivity() {
  const [grid, setGrid] = useState<Served<Grid> | null>(null);
  const [cands, setCands] = useState<CandidateRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const ctl = new AbortController();
    getSensitivity(ctl.signal)
      .then((g) => {
        setGrid(g);
        setError(null);
      })
      .catch((e: unknown) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)));
    getCandidates(ctl.signal)
      .then((c) => setCands(c.candidates))
      .catch(() => setCands([]));
    return () => ctl.abort();
  }, [attempt]);

  const intro = (
    <div className={l.intro}>
      <div className={l.titleRow}>
        <h1 className={l.h1}>What this search can and can&apos;t find</h1>
        {grid?.demo && <DemoTag />}
      </div>
      <p className={l.lede}>
        We hide fake planets in real TESS light curves and count how many the nightly search finds again. Each square is the share it recovered, by planet size and
        orbital period.
      </p>
    </div>
  );

  if (error) {
    return (
      <>
        {intro}
        <LoadError what="The recovery map" error={error} onRetry={() => setAttempt((n) => n + 1)} />
      </>
    );
  }
  if (!grid) {
    return (
      <>
        {intro}
        <div className={l.skeleton} style={{ height: 420 }} role="status" aria-label="Loading the recovery map" />
      </>
    );
  }

  const g = grid.data;
  const R = g.radius_edges_rearth;
  const P = g.period_edges_d;
  const nR = R.length - 1;
  const nP = P.length - 1;
  // Big planets at the top: draw rows from the largest radius bin down.
  const rowsTopDown = Array.from({ length: nR }, (_, k) => nR - 1 - k);
  const marks = cands.flatMap((c) => {
    const px = binPos(P, c.period_d);
    const py = binPos(R, rEarth(c.radius_rjup));
    return px == null || py == null ? [] : [{ c, left: px * 100, top: (1 - py) * 100 }];
  });

  return (
    <>
      {intro}
      <div className={s.sensWrap}>
        <figure style={{ margin: 0, minWidth: 0 }}>
          <div className={s.sens}>
            <span className={`label ${s.sensYTitle}`}>Planet size, × Earth</span>
            <div className={s.sensY} aria-hidden>
              {R.map((v, i) => (
                <span key={v} style={{ top: `${(1 - i / nR) * 100}%` }}>
                  {fmtEdge(v)}
                </span>
              ))}
            </div>
            <div
              className={s.sensArea}
              style={{ gridTemplateColumns: `repeat(${nP}, minmax(0, 1fr))` }}
              role="table"
              aria-label="Share of injected planets recovered, by size (rows) and period (columns)"
            >
              {rowsTopDown.map((i) => (
                <div key={i} role="row" style={{ display: "contents" }}>
                  {g.recovery_pct[i].map((p, j) => (
                    <div
                      key={j}
                      role="cell"
                      className={s.sensCell}
                      style={{ background: cellFill(p), color: p > 55 ? "var(--bg)" : "var(--ink-secondary)" }}
                      title={`${fmtEdge(R[i])} to ${fmtEdge(R[i + 1])} × Earth, ${fmtPeriod(P[j])} to ${fmtPeriod(P[j + 1])}: ${p}% of ${g.n_injected[i][j]} found`}
                      aria-label={`${fmtEdge(R[i])} to ${fmtEdge(R[i + 1])} times Earth, periods ${fmtPeriod(P[j])} to ${fmtPeriod(P[j + 1])}: ${Math.round(p)} percent found`}
                    >
                      {Math.round(p)}
                    </div>
                  ))}
                </div>
              ))}
              {marks.map(({ c, left, top }) => (
                <span key={c.id} className={s.sensMark} style={{ left: `${left}%`, top: `${top}%` }} title={`TIC ${c.tic}`} aria-hidden />
              ))}
            </div>
            <div className={s.sensX} aria-hidden>
              {P.map((v, j) => (
                <span key={v} style={{ left: `${(j / nP) * 100}%` }}>
                  {fmtEdge(v)}
                </span>
              ))}
            </div>
            <span className={`label ${s.sensXTitle}`}>Orbital period, days</span>
          </div>
        </figure>

        <div className={s.sensSide}>
          <div>
            <h2>How to read it</h2>
            <p>
              Numbers are the percent found. Top left, big planets on short orbits, are almost always found. Small planets and long orbits fade out: their dips are
              shallow or too rare.
            </p>
          </div>
          <div>
            <h2>Why long orbits drop off</h2>
            <p>
              The search needs at least three dips, and TESS watches most stars for about 27 days at a time. A planet on a 20-day orbit shows two dips at best, so
              it is mostly missed.
            </p>
          </div>
          <div>
            <h2>Our candidates</h2>
            <p>
              <span className={s.sensMark} style={{ position: "relative", display: "inline-block", margin: "0 6px 0 2px", verticalAlign: "-1px" }} aria-hidden />
              Each diamond is one of the <Link href="/finder">current candidates</Link>, placed by its size and period.
            </p>
          </div>
          <p className={l.help}>
            {nf0.format(g.n_injected.flat().reduce((a, b) => a + b, 0))} fake planets hidden in the light curves of {nf0.format(g.stars_used)} stars, run{" "}
            {formatUtc(g.run_at).split(",")[0]}.
            {grid.demo && " Demo: the grid is a stand-in model until the Finder service publishes its real run."}
          </p>
        </div>
      </div>
    </>
  );
}

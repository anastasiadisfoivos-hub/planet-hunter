"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { getMonitorCoverage, getMonitorLog, getStarCurve, type LogStar, type MonitorCoverage, type StarOutcome } from "@/lib/api";
import { Coverage } from "./Coverage";
import { fmtDateTime, fmtDay, OUTCOME_WORD, sectorWord, starKind, thousands } from "./format";
import { Tick } from "./MonitorScreen";
import s from "./log.module.css";

const PAGE = 60;
type Filter = "all" | StarOutcome;
const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "candidate", label: "Candidates" },
  { id: "known", label: "Known" },
  { id: "rejected", label: "Rejected" },
  { id: "none", label: "Nothing found" },
];

/** A row's little trace: the star's own light curve if we have it, otherwise a flat rule. */
function Spark({ tic }: { tic: number }) {
  const ref = useRef<SVGSVGElement>(null);
  const [d, setD] = useState<string | null>(null);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ac = new AbortController();
    const io = new IntersectionObserver(
      ([e]) => {
        if (!e.isIntersecting) return;
        io.disconnect();
        getStarCurve(tic, ac.signal).then((star) => {
          const lc = star?.lightcurve;
          if (!lc || !lc.t.length) return;
          const n = 160;
          const step = Math.max(1, Math.floor(lc.f.length / n));
          const pts: number[] = [];
          for (let i = 0; i < lc.f.length; i += step) {
            let m = Infinity;
            for (let k = i; k < Math.min(i + step, lc.f.length); k++) m = Math.min(m, lc.f[k]);
            pts.push(m);
          }
          const sorted = [...pts].sort((a, b) => a - b);
          const lo = sorted[0];
          const hi = sorted[Math.floor(sorted.length * 0.98)];
          const span = hi - lo || 1e-3;
          setD(pts.map((v, i) => `${i ? "L" : "M"}${((i / (pts.length - 1)) * 200).toFixed(1)} ${(2 + ((hi - v) / span) * 20).toFixed(1)}`).join(""));
        });
      },
      { rootMargin: "200px" },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      ac.abort();
    };
  }, [tic]);
  return (
    <svg ref={ref} viewBox="0 0 200 24" preserveAspectRatio="none" className={s.spark} aria-hidden>
      {d ? <path d={d} /> : <line x1={0} x2={200} y1={12} y2={12} className={s.flat} />}
    </svg>
  );
}

function Row({ star }: { star: LogStar }) {
  const lead = star.detections.find((d) => d.outcome === star.outcome) ?? star.detections[0];
  return (
    <li className={s.row}>
      <span className={s.when}>
        <span className="num">{fmtDay(star.searched_at).toUpperCase()}</span>
        <span className="num quiet">{star.searched_at.slice(11, 16)}</span>
      </span>
      <span className={s.who}>
        <span className={s.tic}>TIC {star.tic}</span>
        <span className={s.kind}>{starKind(star.teff, star.radius_rsun)}</span>
      </span>
      <span className={`label ${s.sectors}`}>{sectorWord(star.sectors)}</span>
      <Spark tic={star.tic} />
      <span className={s.what}>
        <span className={s.outcome} data-outcome={star.outcome}>
          {star.outcome !== "none" && <Tick outcome={star.outcome} />}
          {OUTCOME_WORD[star.outcome]}
          {star.detections.length > 1 && <span className="quiet"> · {star.detections.length} signals</span>}
        </span>
        {lead && <span className={s.why}>{lead.reason}</span>}
      </span>
    </li>
  );
}

export function Log() {
  const [stars, setStars] = useState<LogStar[] | null>(null);
  const [cov, setCov] = useState<MonitorCoverage | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [shown, setShown] = useState(PAGE);
  useEffect(() => {
    const ac = new AbortController();
    getMonitorLog(ac.signal)
      .then((l) => setStars(l.stars))
      .catch(() => !ac.signal.aborted && setError(true));
    getMonitorCoverage(ac.signal)
      .then(setCov)
      .catch(() => {});
    return () => ac.abort();
  }, []);
  const rows = useMemo(() => (stars ?? []).filter((x) => filter === "all" || x.outcome === filter), [stars, filter]);
  const span = stars?.length ? `${fmtDateTime(stars[stars.length - 1].searched_at)} to ${fmtDateTime(stars[0].searched_at)}` : null;

  return (
    <div className={`wrap ${s.page}`}>
      <header className={s.head}>
        <h1>Log</h1>
        <div className="prose">
          <p>Every star the search has looked at, newest at the top: when it was searched, the TESS data it used, and what it made of it.</p>
          {span && <p className="label">{`${thousands(stars!.length)} stars · ${span}`}</p>}
        </div>
      </header>

      <section aria-labelledby="where" className={s.where}>
        <h2 id="where">Where it has looked</h2>
        {cov ? <Coverage stars={cov.stars} /> : <div className={s.skyWait} aria-hidden />}
      </section>

      <section aria-labelledby="rows" className={s.rowsSec}>
        <div className={s.rowsHead}>
          <h2 id="rows">Star by star</h2>
          <div className={s.filters} role="group" aria-label="Show">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={s.filter}
                aria-pressed={filter === f.id}
                onClick={() => {
                  setFilter(f.id);
                  setShown(PAGE);
                }}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        {error && <p className="italic quiet">The log could not be loaded. Try again in a minute.</p>}
        {!stars && !error && <div className={s.skyWait} role="status" aria-label="Loading the log" />}
        {stars && rows.length === 0 && <p className="italic quiet">No star in the log has this outcome yet.</p>}
        <ol className={s.rows}>
          {rows.slice(0, shown).map((x) => (
            <Row key={`${x.tic}-${x.searched_at}`} star={x} />
          ))}
        </ol>
        {rows.length > shown && (
          <button type="button" className="btn" onClick={() => setShown((n) => n + PAGE)}>
            Show {Math.min(PAGE, rows.length - shown)} more
          </button>
        )}
      </section>
    </div>
  );
}

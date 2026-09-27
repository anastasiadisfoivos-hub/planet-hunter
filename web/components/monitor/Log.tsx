"use client";

import { useEffect, useMemo, useState } from "react";
import { getMonitorCoverage, getMonitorLog, getQueueCoverage, getSparks, type LogStar, type MonitorCoverage, type QueueCoverage, type Sparks, type StarOutcome } from "@/lib/api";
import { Coverage } from "./Coverage";
import { fmtDateTime, fmtDay, fmtTemp, OUTCOME_WORD, queueLine, sectorWord, starKind, thousands } from "./format";
import { StarGlyph } from "./Glyphs";
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

/** A row's trace: the star's whole curve in 180 points, or a clear mark when none is stored. */
function Spark({ values }: { values: number[] | undefined }) {
  const d = useMemo(() => {
    if (!values?.length) return null;
    const sorted = [...values].sort((a, b) => a - b);
    const lo = sorted[0];
    const hi = sorted[Math.floor(sorted.length * 0.97)];
    const span = hi - lo || 1;
    return values.map((v, i) => `${i ? "L" : "M"}${((i / (values.length - 1)) * 240).toFixed(1)} ${(3 + ((hi - Math.min(v, hi)) / span) * 30).toFixed(1)}`).join("");
  }, [values]);
  if (!d)
    return (
      <span className={s.noCurve}>
        <span className="label">no curve stored</span>
      </span>
    );
  return (
    <svg viewBox="0 0 240 36" preserveAspectRatio="none" className={s.spark} role="img" aria-label="The star's light curve, whole">
      <path d={d} />
    </svg>
  );
}

function Row({ star, spark }: { star: LogStar; spark: number[] | undefined }) {
  const lead = star.detections.find((d) => d.outcome === star.outcome) ?? star.detections[0];
  const n = star.detections.length;
  return (
    <li className={s.row}>
      <span className={s.when}>
        <span className="num">{fmtDay(star.searched_at).toUpperCase()}</span>
        <span className="num quiet">{star.searched_at.slice(11, 16)} UTC</span>
      </span>
      <span className={s.who}>
        <StarGlyph teff={star.teff} radius={star.radius_rsun} size={34} />
        <span className={s.whoText}>
          <span className={s.tic}>TIC {star.tic}</span>
          <span className={s.kind}>
            {starKind(star.teff, star.radius_rsun)}
            {star.teff != null && <span className="num"> · {fmtTemp(star.teff)}</span>}
          </span>
        </span>
      </span>
      <span className={`label ${s.sectors}`}>{sectorWord(star.sectors)}</span>
      <Spark values={spark} />
      <span className={s.what}>
        <span className={s.outcome} data-outcome={star.outcome}>
          {star.outcome !== "none" && <Tick outcome={star.outcome} />}
          {OUTCOME_WORD[star.outcome]}
          {n > 1 && <span className={s.count}> · {n} signals</span>}
        </span>
        {lead && <span className={s.why}>{lead.reason}</span>}
      </span>
    </li>
  );
}

/** How far each search has gone down its own list, from the search server's ledger. */
function QueueList({ q }: { q: QueueCoverage }) {
  return (
    <div className={s.queues}>
      <ul className="prose">
        {Object.entries(q.queues).map(([name, c]) => (
          <li key={name}>{queueLine(name, c)}</li>
        ))}
      </ul>
      {q.updated_at && <p className="label quiet">From the search server&apos;s ledger, {fmtDateTime(q.updated_at)}</p>}
    </div>
  );
}

export function Log() {
  const [stars, setStars] = useState<LogStar[] | null>(null);
  const [cov, setCov] = useState<MonitorCoverage | null>(null);
  const [sparks, setSparks] = useState<Sparks | null>(null);
  const [queues, setQueues] = useState<QueueCoverage | null>(null);
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
    getSparks().then(setSparks);
    getQueueCoverage(ac.signal).then(setQueues);
    return () => ac.abort();
  }, []);
  const rows = useMemo(() => (stars ?? []).filter((x) => filter === "all" || x.outcome === filter), [stars, filter]);
  const teffOf = useMemo(() => new Map((stars ?? []).map((x) => [x.tic, x.teff])), [stars]);
  const span = stars?.length ? `${fmtDateTime(stars[stars.length - 1].searched_at)} to ${fmtDateTime(stars[0].searched_at)}` : null;

  return (
    <div className={`wrap ${s.page}`}>
      <header className={s.head}>
        <h1>Log</h1>
        <div className={s.lead}>
          <p>Every star the search has looked at, newest at the top: when it was searched, the TESS data it used, its whole light curve, and what the search made of it.</p>
          {span && <p className="label">{`${thousands(stars!.length)} stars · ${span}`}</p>}
        </div>
      </header>

      <section aria-labelledby="where" className={s.where}>
        <h2 id="where">Where it has looked</h2>
        {cov ? <Coverage stars={cov.stars} teffOf={teffOf} /> : <div className={s.skyWait} aria-hidden />}
        {queues && Object.keys(queues.queues).length > 0 && <QueueList q={queues} />}
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
        <div className={s.colHead} aria-hidden>
          <span className="label">Searched</span>
          <span className="label">Star</span>
          <span className="label">TESS data</span>
          <span className="label">Light curve</span>
          <span className="label">What the search made of it</span>
        </div>
        {error && <p className="italic quiet">The log could not be loaded. Try again in a minute.</p>}
        {!stars && !error && <div className={s.skyWait} role="status" aria-label="Loading the log" />}
        {stars && rows.length === 0 && <p className="italic quiet">No star in the log has this outcome yet.</p>}
        <ol className={s.rows}>
          {rows.slice(0, shown).map((x) => (
            <Row key={`${x.tic}-${x.searched_at}`} star={x} spark={sparks?.stars[String(x.tic)]} />
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

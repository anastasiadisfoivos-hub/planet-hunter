"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { getMonitorNow, getMonitorStats, type Detection, type MonitorNow, type MonitorStats } from "@/lib/api";
import { MonitorClient } from "./client";
import { detectionLabel, modeLabel, modeShort, OUTCOME_WORD, plural, thousands } from "./format";
import { StarHeader } from "./StarHeader";
import { StillTrace } from "./Recorder";
import s from "./monitor.module.css";

export function Tick({ outcome }: { outcome: Detection["outcome"] }) {
  return <span className={s.tick} data-outcome={outcome} aria-hidden />;
}

/** The dips the search found on this star, in words: the pen's notes. */
export function DipNotes({ dets, shown }: { dets: Detection[]; shown: number }) {
  if (!dets.length) return <p className={`${s.note} italic quiet`}>No dip stood out from the noise on this star.</p>;
  const list = dets.slice(0, shown);
  if (!list.length) return <p className={`${s.note} italic quiet`}>Searching this star.</p>;
  return (
    <ol className={s.notes}>
      {list.map((d, i) => (
        <li key={i} className={s.noteRow}>
          <span className={s.noteHead}>
            <Tick outcome={d.outcome} />
            <span className="label" data-outcome={d.outcome}>
              {OUTCOME_WORD[d.outcome]}
            </span>
            <span className="num quiet">{detectionLabel(d)}</span>
          </span>
          <span className={`${s.reason} italic`}>{d.reason}</span>
        </li>
      ))}
    </ol>
  );
}

function Tally({ stats }: { stats: MonitorStats | null }) {
  if (!stats) return <p className={s.tally} aria-hidden />;
  return (
    <p className={s.tally}>
      <span>
        <span className="num">{thousands(stats.stars_searched)}</span> <span className="label">stars searched</span>
      </span>
      <span>
        <span className="num">{thousands(stats.signals)}</span> <span className="label">signals</span>
      </span>
      <span>
        <span className="num">{thousands(stats.candidates)}</span> <span className="label">{stats.candidates === 1 ? "new candidate" : "new candidates"}</span>
      </span>
    </p>
  );
}

export function MonitorScreen() {
  const client = useRef<MonitorClient | null>(null);
  const [now, setNow] = useState<MonitorNow | null>(null);
  const [stats, setStats] = useState<MonitorStats | null>(null);
  const [failing, setFailing] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    const ac = new AbortController();
    const c = new MonitorClient(getMonitorNow);
    c.onRetry = () => setFailing(true);
    client.current = c;
    c.start(ac.signal)
      .then((n) => {
        setFailing(false);
        setNow(n);
      })
      .catch(() => {});
    getMonitorStats(ac.signal).then(setStats).catch(() => {});
    return () => ac.abort();
  }, []);

  const next = useCallback(() => {
    const c = client.current;
    if (!c || busy) return;
    setBusy(true);
    c.advance()
      .then((n) => {
        setFailing(false);
        setNow(n);
      })
      .finally(() => setBusy(false));
  }, [busy]);

  const star = now?.star ?? null;
  return (
    <section className={s.monitor} aria-label="Monitor">
      <div className={`wrap ${s.head}`}>
        {star ? <StarHeader star={star} /> : <div className={s.starHead} aria-busy="true" />}
        <div className={s.mode}>
          {now && (
            <>
              <p className={s.modeTag} data-mode={now.mode}>
                {now.mode === "live" && <span className={s.liveDot} aria-hidden />}
                {modeShort(now.mode)}
              </p>
              <p className={s.modeLine}>{modeLabel(now.mode, now.replay_of)}</p>
            </>
          )}
          <div className={s.controls}>
            <button type="button" className="btn" onClick={next} disabled={!now || busy}>
              Next star
            </button>
          </div>
        </div>
      </div>

      <div className={s.paper}>
        {star?.lightcurve ? (
          <StillTrace
            star={star}
            label={`Light curve of TIC ${star.tic}: brightness against time. ${plural(star.detections.length, "signal")} marked.`}
          />
        ) : (
          <div className={s.canvas} aria-hidden />
        )}
      </div>

      <div className={`wrap ${s.foot}`}>
        <Tally stats={stats} />
        <div className={s.pen}>
          {failing && <p className={`${s.note} italic quiet`} role="status">The monitor can&apos;t reach the search right now. Trying again.</p>}
          {star && <DipNotes dets={star.detections} shown={star.detections.length} />}
          {star && star.outcome !== "none" && (
            <p className={s.more}>
              <Link href="/log">Every star searched</Link>
              {star.outcome === "candidate" && (
                <>
                  {" "}
                  · <Link href="/candidates">Candidates</Link>
                </>
              )}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { getMonitorNow, getMonitorStats, type Detection, type MonitorNow, type MonitorStar, type MonitorStats } from "@/lib/api";
import { MonitorClient } from "./client";
import { btjdToMs, detectionLabel, detectionSentence, modeLabel, modeShort, observedLine, OUTCOME_WORD, plural, starKind, thousands } from "./format";
import { StarHeader } from "./StarHeader";
import { StillTrace, StreamTrace } from "./Recorder";
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

/** True while the viewer asks for reduced motion; follows the setting live. */
function useReducedMotion(): boolean | null {
  const [rm, setRm] = useState<boolean | null>(null);
  useEffect(() => {
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const on = () => setRm(mq.matches);
    on();
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return rm;
}

export function MonitorScreen() {
  const client = useRef<MonitorClient | null>(null);
  const [now, setNow] = useState<MonitorNow | null>(null);
  const [stats, setStats] = useState<MonitorStats | null>(null);
  const [failing, setFailing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [paused, setPaused] = useState(false);
  /** Detections the pen has reached on this star, in the order it reached them. */
  const [reached, setReached] = useState<{ tic: number; dets: number[] }>({ tic: 0, dets: [] });
  const [said, setSaid] = useState("");
  const lastSaid = useRef(0);
  const rm = useReducedMotion();

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

  const rmStill = rm === true;
  /** The star on the paper: in a stream it changes when the paper has advanced, not when the data arrives. */
  const [drawn, setDrawn] = useState<MonitorStar | null>(null);
  const incoming = now?.star ?? null;
  const star = rmStill ? incoming : (drawn ?? null);

  // the live text twin: says each new star, and each dip, politely and not more than once every 2 s
  const say = useCallback((text: string, force = false) => {
    const t = Date.now();
    if (!force && t - lastSaid.current < 2000) return;
    lastSaid.current = t;
    setSaid(text);
  }, []);

  useEffect(() => {
    if (!star) return;
    say(`Now drawing TIC ${star.tic}, ${starKind(star.teff, star.radius_rsun)}, ${observedLine(star.observed_from, star.observed_to, star.sectors)}.`, true);
  }, [star, say]);

  const next = useCallback(() => {
    const c = client.current;
    if (!c || busy) return;
    setBusy(true);
    c.advance()
      .then((n) => {
        setFailing(false);
        setNow(n);
      })
      .catch(() => {})
      .finally(() => setBusy(false));
  }, [busy]);

  const onMark = useCallback(
    (on: MonitorStar, det: number) => {
      setReached((r) => (r.tic !== on.tic ? { tic: on.tic, dets: [det] } : r.dets.includes(det) ? r : { tic: on.tic, dets: [...r.dets, det] }));
      const d = on.detections[det];
      if (d) say(detectionSentence(d, btjdToMs(d.t0)));
    },
    [say],
  );

  const still = rmStill;
  const shownDets = star ? (still ? star.detections : reached.tic === star.tic ? reached.dets.map((k) => star.detections[k]) : []) : [];
  const label = star ? `Light curve of TIC ${star.tic}: brightness against time, ${plural(star.detections.length, "signal")} marked.` : "";

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === " " && !still) {
      e.preventDefault();
      setPaused((p) => !p);
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      next();
    }
  };

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
            {!still && (
              <button type="button" className="btn" onClick={() => setPaused((p) => !p)} aria-pressed={paused} disabled={!now}>
                {paused ? "Resume" : "Pause"}
              </button>
            )}
            <button type="button" className="btn" onClick={next} disabled={!now || busy}>
              Next star
            </button>
          </div>
        </div>
      </div>

      <div className={s.paper} tabIndex={0} onKeyDown={onKey} aria-label="Light curve. Space pauses, the right arrow skips to the next star." role="group">
        {incoming?.lightcurve && rm !== null ? (
          still ? (
            <StillTrace star={incoming} label={label} />
          ) : (
            <StreamTrace star={incoming} paused={paused} onFinished={next} onMark={onMark} onStart={setDrawn} label={label} />
          )
        ) : (
          <div className={s.canvas} aria-hidden />
        )}
        {paused && !still && <p className={`label ${s.pausedTag}`}>Paused</p>}
      </div>
      <p className="sr-only" aria-live="polite">
        {said}
      </p>

      <div className={`wrap ${s.foot}`}>
        <Tally stats={stats} />
        <div className={s.pen}>
          {failing && <p className={`${s.note} italic quiet`} role="status">The monitor can&apos;t reach the search right now. Trying again.</p>}
          {star &&
            (star.detections.length > 0 && shownDets.length === 0 ? (
              <p className={`${s.note} italic quiet`}>Reading this star&apos;s light.</p>
            ) : (
              <DipNotes dets={shownDets} shown={shownDets.length} />
            ))}
          {star && (
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

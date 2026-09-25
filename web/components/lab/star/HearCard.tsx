"use client";

import { useEffect, useMemo, useState } from "react";
import { CheckCircle, Circle, CircleNotch } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { analyze, getJob, STEPS, type AnalyzeJob, type StarLab, type StarLightcurve } from "@/lib/api";
import { LightCurvePlayer, type Track } from "../HearStar";
import { Card } from "./Card";
import { matchPlanet } from "./MeasureCard";
import { lightcurveReason } from "./shared";
import s from "./star.module.css";
import l from "../lab.module.css";

const LEDE = "Its own light curve played as sound. Brightness is pitch, so each time a planet crosses the star you hear the note drop.";

/** Runs the real analysis job for this star and reports when it is done. */
function AnalyzeAction({ lab, onDone }: { lab: StarLab; onDone: () => void }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [job, setJob] = useState<AnalyzeJob | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!jobId) return;
    let live = true;
    let timer = 0;
    const poll = () =>
      getJob(jobId)
        .then((j) => {
          if (!live) return;
          setJob(j);
          if (j.status === "done") onDone();
          else if (j.status === "failed") setError("The analysis stopped before it finished.");
          else timer = window.setTimeout(poll, 700);
        })
        .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [jobId, onDone]);

  const start = () => {
    setError(null);
    setJob(null);
    setJobId(null);
    analyze({ name: lab.name, tic_id: lab.tic, ra_deg: 0, dec_deg: 0 })
      .then((r) => setJobId(r.job_id))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  };

  const running = jobId && !error;
  const steps = job?.steps ?? STEPS.map((st) => ({ key: st.key, label: st.label, state: "pending" as const, seconds: null }));
  return (
    <>
      {!running && (
        <Button variant="primary" onClick={start}>
          {error ? "Try the analysis again" : "Analyze this star (1 to 3 min)"}
        </Button>
      )}
      {running && (
        <ol className={s.steps} aria-live="polite" aria-label="Analysis progress">
          {steps.map((st) => (
            <li key={st.key} data-state={st.state}>
              {st.state === "done" ? <CheckCircle size={16} weight="fill" aria-hidden /> : st.state === "running" ? <CircleNotch size={16} className={s.spin} aria-hidden /> : <Circle size={16} aria-hidden />}
              <span>{st.label}</span>
              <span className="mono">{st.seconds != null ? `${st.seconds.toFixed(1)} s` : ""}</span>
            </li>
          ))}
        </ol>
      )}
      {error && (
        <p className={l.help} role="alert">
          {error}
        </p>
      )}
      <p className={l.help}>Downloads its TESS light curve and searches it for repeating dips. This card, and Measure its planet, unlock when it finishes.</p>
    </>
  );
}

export function HearCard({ lab, lc, standIn, lcError, onRetry, onAnalyzed }: {
  lab: StarLab;
  lc: StarLightcurve | null;
  standIn: string | null;
  lcError: string | null;
  onRetry: () => void;
  onAnalyzed: () => void;
}) {
  const sig = lab.signals[0];
  const track = useMemo<Track | null>(
    () =>
      lc && {
        name: standIn ?? lab.name,
        time: lc.unfolded.time_btjd,
        flux: lc.unfolded.flux,
        signal: sig ? { period: sig.period_d, t0: sig.t0, duration: sig.duration_h / 24, depth: sig.depth_ppm * 1e-6 } : null,
        planet: sig ? (matchPlanet(sig, lab.known_planets)?.name ?? null) : null,
      },
    [lc, sig, lab.name, lab.known_planets, standIn],
  );

  if (!lab.lightcurve.available) {
    return (
      <Card id="hear" title="Hear it" lede={LEDE} locked={lightcurveReason(lab)}>
        {lab.lightcurve.reason_if_not === "not_analyzed" ? (
          <AnalyzeAction lab={lab} onDone={onAnalyzed} />
        ) : (
          <p className={l.help}>Nothing here can unlock it: the Lab only plays light curves TESS has actually measured.</p>
        )}
      </Card>
    );
  }
  return (
    <Card id="hear" title="Hear it" data={standIn ? "demo" : "real"} lede={LEDE}>
      {standIn && (
        <p className={l.help}>
          Demo: the analysis service isn&apos;t connected, so the stored TESS light curve of {standIn} plays in place of {lab.name}&apos;s.
        </p>
      )}
      <LightCurvePlayer track={track} error={lcError} onRetry={onRetry} />
    </Card>
  );
}

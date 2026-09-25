"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { Info, Pause, Play, SpeakerHigh } from "@phosphor-icons/react";
import { Button, Segmented } from "@/components/ui";
import { linear, LoadError, Note, nf0, Skeleton, ticks, XAxis, YAxis } from "./chart";
import { useJson, useReducedMotion, useWidth } from "./hooks";
import { foldAndBin, pitchFor } from "./physics";
import s from "./lab.module.css";

type Result = {
  target: { tic_id: number; query: string; teff_k: number; stellar_radius_rsun: number };
  data: { sector: number; author: string; exptime: number }[];
  discoveries: {
    name_if_known: string | null;
    light_curve: { time_btjd: number[]; flux: number[] };
    raw: { signal: { period: number; t0: number; duration: number; depth: number; n_transits: number }; radius_rjup: number };
  }[];
};

const TARGETS = [
  { value: "wasp-18", label: "WASP-18" },
  { value: "wasp-121", label: "WASP-121" },
] as const;
type Target = (typeof TARGETS)[number]["value"];
type Mode = "raw" | "folded";
const SPEEDS = [
  { value: "0.5", label: "0.5×" },
  { value: "1", label: "1×" },
  { value: "2", label: "2×" },
  { value: "4", label: "4×" },
];
/** Seconds of sound for the whole plot at 1×. */
const DURATION: Record<Mode, number> = { raw: 40, folded: 10 };
const VOLUME = 0.12;
/** Chart margins, shared by the plot and the playhead loop. */
const M = { l: 52, r: 12, t: 28, b: 44 };

type Series = { x: number[]; y: number[]; minY: number; maxY: number; gaps: Set<number> };

function makeSeries(r: Result, mode: Mode): Series {
  const d = r.discoveries[0];
  const { time_btjd: t, flux: f } = d.light_curve;
  const { period, t0 } = d.raw.signal;
  let x: number[];
  let y: number[];
  if (mode === "folded") {
    const b = foldAndBin(t, f, period, t0, 180);
    // Hours from the middle of the transit.
    x = b.phase.map((p) => p * period * 24);
    y = b.flux;
  } else {
    x = t;
    y = f;
  }
  // Gaps in the data (between TESS orbits and sectors) are silent.
  const steps = x.slice(1).map((v, i) => v - x[i]).sort((a, b) => a - b);
  const typical = steps[Math.floor(steps.length / 2)] ?? 0;
  const gaps = new Set<number>();
  for (let i = 0; i < x.length - 1; i++) if (x[i + 1] - x[i] > typical * 4) gaps.add(i);
  return { x, y, minY: Math.min(...y), maxY: Math.max(...y), gaps };
}

/** Plays a series as a tone whose pitch follows brightness. One oscillator, scheduled ahead. */
class Voice {
  ctx: AudioContext;
  osc: OscillatorNode | null = null;
  gain: GainNode | null = null;
  startAt = 0;
  from = 0;
  seconds = 1;

  constructor(ctx: AudioContext) {
    this.ctx = ctx;
  }

  play(sr: Series, from: number, seconds: number, onEnd: () => void) {
    this.stop();
    const ctx = this.ctx;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = "triangle";
    osc.connect(gain).connect(ctx.destination);
    const x0 = sr.x[0];
    const span = sr.x[sr.x.length - 1] - x0;
    const T0 = ctx.currentTime + 0.05;
    const at = (i: number) => T0 + (((sr.x[i] - x0) / span - from) * seconds);
    const first = sr.x.findIndex((v) => (v - x0) / span >= from);
    const f = (i: number) => pitchFor(sr.y[i], sr.minY, sr.maxY);
    osc.frequency.setValueAtTime(f(Math.max(0, first)), T0);
    gain.gain.setValueAtTime(0, T0);
    gain.gain.linearRampToValueAtTime(VOLUME, T0 + 0.04);
    for (let i = Math.max(0, first); i < sr.x.length; i++) {
      osc.frequency.linearRampToValueAtTime(f(i), at(i));
      if (sr.gaps.has(i) && i + 1 < sr.x.length) {
        gain.gain.setValueAtTime(VOLUME, at(i));
        gain.gain.linearRampToValueAtTime(0, at(i) + 0.03);
        gain.gain.setValueAtTime(0, at(i + 1) - 0.03);
        gain.gain.linearRampToValueAtTime(VOLUME, at(i + 1));
        osc.frequency.setValueAtTime(f(i + 1), at(i + 1) - 0.03);
      }
    }
    const end = T0 + (1 - from) * seconds;
    gain.gain.setValueAtTime(VOLUME, end - 0.04);
    gain.gain.linearRampToValueAtTime(0, end);
    osc.start(T0);
    osc.stop(end + 0.05);
    osc.onended = () => {
      if (this.osc === osc) {
        this.osc = null;
        onEnd();
      }
    };
    this.osc = osc;
    this.gain = gain;
    this.startAt = T0;
    this.from = from;
    this.seconds = seconds;
  }

  /** Where the playhead is, 0..1. */
  position(): number {
    return Math.min(1, Math.max(0, this.from + (this.ctx.currentTime - this.startAt) / this.seconds));
  }

  stop() {
    const osc = this.osc;
    const gain = this.gain;
    this.osc = null;
    if (!osc || !gain) return;
    const t = this.ctx.currentTime;
    gain.gain.cancelScheduledValues(t);
    gain.gain.setValueAtTime(gain.gain.value, t);
    gain.gain.linearRampToValueAtTime(0, t + 0.03);
    osc.stop(t + 0.04);
  }
}

function LightCurve({ sr, mode, result, pos, onSeek, headRef, valueRef }: {
  sr: Series;
  mode: Mode;
  result: Result;
  pos: number;
  onSeek: (frac: number) => void;
  headRef: React.RefObject<SVGGElement | null>;
  valueRef: React.RefObject<HTMLSpanElement | null>;
}) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = w < 520 ? 240 : 320;
  const m = M;
  const x0 = sr.x[0];
  const x1 = sr.x[sr.x.length - 1];
  const x = linear([x0, x1], [m.l, w - m.r]);
  const pad = (sr.maxY - sr.minY) * 0.08;
  const y = linear([sr.minY - pad, sr.maxY + pad], [h - m.b, m.t]);
  const sig = result.discoveries[0].raw.signal;

  // One path, broken at data gaps.
  const d = sr.x.map((v, i) => `${i === 0 || sr.gaps.has(i - 1) ? "M" : "L"}${x(v).toFixed(1)},${y(sr.y[i]).toFixed(1)}`).join("");
  const transits = useMemo(() => {
    if (mode !== "raw") return [];
    const out: number[] = [];
    for (let n = Math.ceil((x0 - sig.t0) / sig.period); sig.t0 + n * sig.period <= x1; n++) out.push(sig.t0 + n * sig.period);
    return out;
  }, [mode, x0, x1, sig.t0, sig.period]);

  const seek = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    onSeek(Math.min(1, Math.max(0, (e.clientX - r.left - m.l) / (w - m.l - m.r))));
  };

  const xt = mode === "raw" ? ticks(x0, x1, w < 520 ? 4 : 8) : ticks(x0, x1, w < 520 ? 4 : 6);
  const yt = ticks(sr.minY - pad, sr.maxY + pad, 4);
  const headX = m.l + pos * (w - m.l - m.r);
  const inTransit = (v: number) => v < 1 - sig.depth * 0.4;
  const idx = Math.min(sr.x.length - 1, Math.max(0, sr.x.findIndex((v) => v >= x0 + pos * (x1 - x0))));

  return (
    <div ref={ref}>
      <svg
        className={s.svg}
        width={w}
        height={h}
        role="img"
        aria-label={
          mode === "raw"
            ? `Brightness of ${result.target.query} over ${Math.round(x1 - x0)} days, with ${transits.length} dips where the planet passes in front.`
            : `Brightness of ${result.target.query} with every transit stacked: one dip of ${(sig.depth * 100).toFixed(2)}% lasting about ${(sig.duration * 24).toFixed(1)} hours.`
        }
        style={{ cursor: "pointer" }}
        onPointerDown={seek}
      >
        <XAxis
          x={x}
          y={h - m.b}
          values={xt}
          format={(v) => (mode === "raw" ? `${nf0.format(v - x0)}` : `${v > 0 ? "+" : ""}${v}`)}
          title={mode === "raw" ? "Days since the first point" : "Hours from mid-transit"}
        />
        <YAxis y={y} x={m.l} values={yt} format={(v) => `${(v * 100).toFixed(1)}%`} grid={[m.l, w - m.r]} title="Brightness" />
        {transits.map((t) => (
          <line key={t} x1={x(t)} x2={x(t)} y1={h - m.b - 6} y2={h - m.b} stroke="var(--accent)" strokeWidth={1.5} />
        ))}
        <path d={d} fill="none" stroke="var(--ink-secondary)" strokeWidth={mode === "raw" ? 1 : 1.75} strokeLinejoin="round" />
        {mode === "folded" && sr.x.map((v, i) => <circle key={i} cx={x(v)} cy={y(sr.y[i])} r={1.6} fill={inTransit(sr.y[i]) ? "var(--accent)" : "var(--ink-muted)"} />)}
        <g ref={headRef} style={{ transform: `translateX(${headX}px)` }}>
          <line x1={0} x2={0} y1={m.t - 6} y2={h - m.b} stroke="var(--accent)" strokeWidth={2} />
          <path d="M-5,-2 L5,-2 L0,5 Z" transform={`translate(0 ${m.t - 6})`} fill="var(--accent)" />
        </g>
      </svg>
      <p className={s.help} style={{ padding: "var(--s-2) var(--s-1) 0" }}>
        Now <span ref={valueRef} className="mono">{(sr.y[idx] * 100).toFixed(2)}%</span>
        {mode === "raw" ? ". Blue ticks mark the transits the analysis found. Click the plot to jump." : ". Blue points are inside the transit. Click the plot to jump."}
      </p>
    </div>
  );
}

export function HearStar() {
  const [target, setTarget] = useState<Target>("wasp-18");
  const [mode, setMode] = useState<Mode>("raw");
  const [speed, setSpeed] = useState("1");
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const reduced = useReducedMotion();
  const { data, error, retry } = useJson<Result>(`/data/lab/${target}.result.json`);
  const sr = useMemo(() => (data ? makeSeries(data, mode) : null), [data, mode]);
  const voice = useRef<Voice | null>(null);
  const headRef = useRef<SVGGElement | null>(null);
  const valueRef = useRef<HTMLSpanElement | null>(null);
  const [audioError, setAudioError] = useState<string | null>(null);

  const seconds = DURATION[mode] / Number(speed);

  const stop = useCallback(() => {
    if (voice.current) {
      setPos(voice.current.osc ? voice.current.position() : 0);
      voice.current.stop();
    }
    setPlaying(false);
  }, []);

  const start = useCallback(
    (from: number) => {
      if (!sr) return;
      try {
        if (!voice.current) voice.current = new Voice(new AudioContext());
        const v = voice.current;
        void v.ctx.resume();
        const at = from >= 0.999 ? 0 : from;
        v.play(sr, at, seconds, () => {
          setPlaying(false);
          setPos(1);
        });
        setPos(at);
        setPlaying(true);
        setAudioError(null);
      } catch (e) {
        setAudioError(e instanceof Error ? e.message : "This browser can't play sound here.");
      }
    },
    [sr, seconds],
  );

  // Changing star or mode stops the sound and rewinds.
  const reset = () => {
    voice.current?.stop();
    setPlaying(false);
    setPos(0);
  };

  // Changing speed while playing carries on from the same place.
  const changeSpeed = (v: string) => {
    setSpeed(v);
    if (playing && voice.current && sr) {
      const p = voice.current.position();
      const secs = DURATION[mode] / Number(v);
      voice.current.play(sr, p, secs, () => {
        setPlaying(false);
        setPos(1);
      });
    }
  };

  // Move the playhead with the sound. Written straight to the DOM, not through React state.
  useEffect(() => {
    if (!playing || !sr) return;
    let raf = 0;
    let lastStep = -1;
    const tick = () => {
      const v = voice.current;
      if (v?.osc) {
        const p = v.position();
        // Reduced motion: the playhead steps four times a second instead of gliding.
        const step = Math.floor(v.ctx.currentTime * 4);
        if (!reduced || step !== lastStep) {
          lastStep = step;
          const svg = headRef.current?.ownerSVGElement;
          if (svg && headRef.current) {
            const w = svg.clientWidth;
            headRef.current.style.transform = `translateX(${M.l + p * (w - M.l - M.r)}px)`;
          }
          const x0 = sr.x[0];
          const span = sr.x[sr.x.length - 1] - x0;
          const i = sr.x.findIndex((x) => (x - x0) / span >= p);
          if (valueRef.current && i >= 0) valueRef.current.textContent = `${(sr.y[i] * 100).toFixed(2)}%`;
        }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, sr, reduced]);

  useEffect(() => () => {
    voice.current?.stop();
    void voice.current?.ctx.close();
  }, []);

  // Stop when the tab is hidden.
  useEffect(() => {
    const onHide = () => document.hidden && stop();
    document.addEventListener("visibilitychange", onHide);
    return () => document.removeEventListener("visibilitychange", onHide);
  }, [stop]);

  const d = data?.discoveries[0];
  const sig = d?.raw.signal;

  return (
    <>
      <div className={s.bench}>
        <section className={s.chartBox} aria-labelledby="lc-h">
          <div className={s.chartHead}>
            <h2 id="lc-h" className={s.h3}>
              {data ? `${data.target.query}, as seen by TESS` : "Light curve"}
            </h2>
            <Segmented
              label="View"
              value={mode}
              onChange={(v) => {
                reset();
                setMode(v);
              }}
              options={[
                { value: "raw", label: "Raw" },
                { value: "folded", label: "Folded" },
              ]}
            />
          </div>
          {error ? (
            <LoadError what="The light curve" error={error} onRetry={retry} />
          ) : sr && data ? (
            <LightCurve
              key={`${target}-${mode}`}
              sr={sr}
              mode={mode}
              result={data}
              pos={pos}
              headRef={headRef}
              valueRef={valueRef}
              onSeek={(f) => (playing ? start(f) : setPos(f))}
            />
          ) : (
            <Skeleton label="Loading the light curve" />
          )}
        </section>

        <aside className={s.side} aria-label="Player">
          <div className={s.block}>
            <Segmented
              label="Star"
              block
              value={target}
              onChange={(v) => {
                reset();
                setTarget(v);
              }}
              options={TARGETS.map((t) => ({ value: t.value, label: t.label }))}
            />
            <div className={s.controls}>
              <Button
                variant="primary"
                icon={playing ? <Pause size={16} weight="fill" /> : <Play size={16} weight="fill" />}
                onClick={() => (playing ? stop() : start(pos))}
                disabled={!sr}
              >
                {playing ? "Pause" : pos > 0 && pos < 1 ? "Resume" : "Play"}
              </Button>
              <Segmented label="Speed" value={speed} onChange={changeSpeed} options={SPEEDS} />
            </div>
            <label className={s.field}>
              <span className="label">Position</span>
              <input
                className={s.range}
                type="range"
                min={0}
                max={1000}
                value={Math.round(pos * 1000)}
                onChange={(e) => {
                  const f = Number(e.target.value) / 1000;
                  if (playing) start(f);
                  else setPos(f);
                }}
                aria-valuetext={`${Math.round(pos * 100)}% of the way through`}
              />
            </label>
            <p className={s.help}>
              <SpeakerHigh size={12} aria-hidden style={{ verticalAlign: "-1px" }} /> Turn your sound on. Nothing plays until you press Play.
            </p>
            {audioError && (
              <p className={s.help} role="alert">
                {audioError}
              </p>
            )}
          </div>

          {d && sig && (
            <div className={s.block}>
              <dl className={s.readout}>
                <div>
                  <dt className="label">Orbit</dt>
                  <dd>{(sig.period * 24).toFixed(1)} h</dd>
                </div>
                <div>
                  <dt className="label">Dip depth</dt>
                  <dd>{(sig.depth * 100).toFixed(2)}%</dd>
                </div>
                <div>
                  <dt className="label">Transits</dt>
                  <dd>{sig.n_transits}</dd>
                </div>
                <div>
                  <dt className="label">Each lasts</dt>
                  <dd>{(sig.duration * 24).toFixed(1)} h</dd>
                </div>
              </dl>
              <p className={s.body}>
                {d.name_if_known ?? "The planet"} passes in front of its star every {(sig.period * 24).toFixed(1)} hours and blocks about{" "}
                {(sig.depth * 100).toFixed(1)}% of its light. The brighter the star, the higher the note, so{" "}
                <strong>every transit is a short drop in pitch</strong>.
              </p>
            </div>
          )}
        </aside>
      </div>

      <section className={s.section} style={{ marginTop: "var(--s-8)" }} aria-labelledby="how-h">
        <div className={s.sectionHead}>
          <h2 id="how-h" className={s.h2}>
            Raw or folded
          </h2>
          <p className={s.body}>
            <strong>Raw</strong> plays the measurements in the order TESS took them, about {DURATION.raw} seconds for {data ? nf0.format(Math.round(data.discoveries[0].light_curve.time_btjd.at(-1)! - data.discoveries[0].light_curve.time_btjd[0])) : "50"} days. Listen for
            the regular drops: that rhythm is the planet&apos;s orbit. The quiet stretches are gaps in the data, while the spacecraft sends its
            pictures home.
          </p>
          <p className={s.body}>
            <strong>Folded</strong> cuts the recording at every orbit and stacks the pieces, so all {sig?.n_transits ?? "the"} transits land on top
            of each other. The noise averages out and one clean dip is left, from the planet&apos;s first edge touching the star to its last.
          </p>
        </div>
        <Note icon={<Info size={14} aria-hidden />}>
          Real data: TESS sectors {data ? data.data.map((x) => x.sector).join(" and ") : "..."}, {data?.data[0]?.exptime ?? 120}-second
          exposures processed by {data?.data[0]?.author ?? "SPOC"}, binned to 30 to 36 minute points by this project&apos;s analysis pipeline. Pitch runs
          from 196 Hz (the faintest point) to 784 Hz (the brightest), two octaves.
        </Note>
      </section>
    </>
  );
}

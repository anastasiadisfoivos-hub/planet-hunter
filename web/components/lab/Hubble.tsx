"use client";

import { useMemo, useRef, useState, type PointerEvent } from "react";
import { Info } from "@phosphor-icons/react";
import { Button, Segmented } from "@/components/ui";
import { linear, log, LoadError, Note, nf0, Skeleton, ticks, XAxis, YAxis } from "./chart";
import { useJson, useWidth } from "./hooks";
import { apparentMag, C_KMS, distanceMpc, fitH0, h0FromPoint, hubbleTimeGyr, rmsResidual, speedKms } from "./physics";
import s from "./lab.module.css";

type HubbleFile = { demo: boolean; note: string; abs_mag: number; supernovae: { name: string; z: number; peak_mag: number }[] };
type View = "measured" | "distance";
type Pt = { name: string; z: number; m: number; d: number; v: number };

const H0_MIN = 30;
const H0_MAX = 150;
const clampH0 = (h: number) => Math.round(Math.min(H0_MAX, Math.max(H0_MIN, h)) * 10) / 10;

function Diagram({ pts, view, h0, fit, absMag, onH0 }: { pts: Pt[]; view: View; h0: number; fit: number | null; absMag: number; onH0: (h: number) => void }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = w < 520 ? 300 : 400;
  const m = { l: 56, r: 16, t: 32, b: 44 };
  const dragging = useRef(false);
  const [hover, setHover] = useState<Pt | null>(null);

  const zMin = 0.006;
  const zMax = 0.12;
  const measured = view === "measured";
  const x = measured ? log([zMin, zMax], [m.l, w - m.r]) : linear([0, 500], [m.l, w - m.r]);
  const y = measured ? linear([12.5, 19.5], [m.t, h - m.b]) : linear([0, 32000], [h - m.b, m.t]);
  const px = (p: Pt) => (measured ? x(p.z) : x(p.d));
  const py = (p: Pt) => (measured ? y(p.m) : y(p.v));

  /** The line for a given H0, as an SVG path. In the measured view it is m = M + 25 + 5 log10(cz / H0). */
  const line = (hh: number) => {
    if (measured) {
      const a = [zMin, zMax].map((z) => `${x(z).toFixed(1)},${y(apparentMag(speedKms(z) / hh, absMag)).toFixed(1)}`);
      return `M${a[0]}L${a[1]}`;
    }
    // Clip the line v = H0 d to the plot box.
    const dEnd = Math.min(500, 32000 / hh);
    return `M${x(0)},${y(0)}L${x(dEnd).toFixed(1)},${y(hh * dEnd).toFixed(1)}`;
  };

  const fromPointer = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const X = e.clientX - r.left;
    const Y = e.clientY - r.top;
    if (measured) {
      const z = x.invert(X);
      return h0FromPoint(distanceMpc(y.invert(Y), absMag), speedKms(z));
    }
    const d = Math.max(1, x.invert(X));
    return h0FromPoint(d, Math.max(0, y.invert(Y)));
  };

  const nearest = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const X = e.clientX - r.left;
    const Y = e.clientY - r.top;
    let best: Pt | null = null;
    let bd = 100;
    for (const p of pts) {
      const dd = (px(p) - X) ** 2 + (py(p) - Y) ** 2;
      if (dd < bd) {
        bd = dd;
        best = p;
      }
    }
    return best;
  };

  const xt = measured ? [0.01, 0.02, 0.05, 0.1] : ticks(0, 500, 5);
  const yt = measured ? ticks(13, 19, 6) : ticks(0, 32000, 4);
  // A grab handle on the user's line, near the right edge of the plot.
  const handle = measured
    ? { x: x(0.08), y: y(apparentMag(speedKms(0.08) / h0, absMag)) }
    : (() => {
        const d = Math.min(420, 30000 / h0);
        return { x: x(d), y: y(h0 * d) };
      })();

  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg
        className={s.svg}
        width={w}
        height={h}
        role="img"
        aria-label={`${pts.length} supernovae. ${measured ? "Fainter ones have larger redshifts." : "Farther ones move away faster."} Your line gives ${nf0.format(h0)} km/s per megaparsec.`}
        style={{ cursor: "grab" }}
        onPointerDown={(e) => {
          dragging.current = true;
          e.currentTarget.setPointerCapture(e.pointerId);
          onH0(clampH0(fromPointer(e)));
        }}
        onPointerMove={(e) => {
          if (dragging.current) onH0(clampH0(fromPointer(e)));
          else if (e.pointerType === "mouse") setHover(nearest(e));
        }}
        onPointerUp={() => (dragging.current = false)}
        onPointerCancel={() => (dragging.current = false)}
        onPointerLeave={() => setHover(null)}
      >
        <defs>
          <clipPath id="plot">
            <rect x={m.l} y={m.t} width={w - m.l - m.r} height={h - m.t - m.b} />
          </clipPath>
        </defs>
        <XAxis
          x={x}
          y={h - m.b}
          values={xt}
          format={(v) => (measured ? String(v) : nf0.format(v))}
          title={measured ? "Redshift, z" : "Distance, Mpc"}
          grid={[m.t, h - m.b]}
        />
        <YAxis y={y} x={m.l} values={yt} format={(v) => (measured ? String(v) : v === 0 ? "0" : `${nf0.format(v / 1000)}k`)} grid={[m.l, w - m.r]} title={measured ? "Peak brightness, mag (brighter up)" : "Speed away, km/s"} />
        <g clipPath="url(#plot)">
          {fit !== null && <path d={line(fit)} stroke="var(--ink-muted)" strokeWidth={1.5} strokeDasharray="5 5" fill="none" />}
          <path d={line(h0)} stroke="var(--ink)" strokeWidth={2} strokeDasharray="6 5" fill="none" />
        </g>
        {pts.map((p) => (
          <circle key={p.name} cx={px(p)} cy={py(p)} r={4} fill="var(--supernova)" stroke="var(--bg-deep)" strokeWidth={1.5} />
        ))}
        {hover && <circle cx={px(hover)} cy={py(hover)} r={7} fill="none" stroke="var(--ink)" strokeWidth={1.25} />}
        <circle cx={handle.x} cy={handle.y} r={7} fill="var(--bg-deep)" stroke="var(--ink)" strokeWidth={2} />
      </svg>
      {hover && (
        <div className={s.tooltip} style={{ left: px(hover), top: py(hover) }}>
          {hover.name}{" "}
          <span className="mono">
            z {hover.z.toFixed(3)}, {hover.m.toFixed(2)} mag, {nf0.format(hover.d)} Mpc
          </span>
        </div>
      )}
    </div>
  );
}

export function Hubble() {
  const { data, error, retry } = useJson<HubbleFile>("/data/lab/hubble.demo.json");
  const [view, setView] = useState<View>("measured");
  const [h0, setH0] = useState(45);
  const [touched, setTouched] = useState(false);
  const [showFit, setShowFit] = useState(false);

  const pts = useMemo<Pt[]>(
    () => (data ? data.supernovae.map((sn) => ({ name: sn.name, z: sn.z, m: sn.peak_mag, d: distanceMpc(sn.peak_mag, data.abs_mag), v: speedKms(sn.z) })) : []),
    [data],
  );
  const best = useMemo(() => (pts.length ? fitH0(pts) : null), [pts]);
  const rms = best !== null ? rmsResidual(pts, h0) : 0;
  const bestRms = best !== null ? rmsResidual(pts, best) : 0;
  const set = (v: number) => {
    setH0(v);
    setTouched(true);
  };

  return (
    <>
      <div className={s.bench}>
        <section className={s.chartBox} aria-labelledby="hd-h">
          <div className={s.chartHead}>
            <h2 id="hd-h" className={s.h3}>
              {view === "measured" ? "How bright, against how redshifted" : "How far, against how fast"}
            </h2>
            <Segmented
              label="Axes"
              value={view}
              onChange={setView}
              options={[
                { value: "measured", label: "As measured" },
                { value: "distance", label: "Distance and speed" },
              ]}
            />
          </div>
          {error ? (
            <LoadError what="The supernovae" error={error} onRetry={retry} />
          ) : data ? (
            <Diagram pts={pts} view={view} h0={h0} fit={showFit ? best : null} absMag={data.abs_mag} onH0={set} />
          ) : (
            <Skeleton label="Loading the supernovae" />
          )}
          <p className={s.help} style={{ padding: "var(--s-2) var(--s-1) 0" }}>
            Drag anywhere on the plot to move the blue line until it runs through the middle of the dots.
          </p>
        </section>

        <aside className={s.side} aria-label="Expansion rate">
          <div className={s.block}>
            <span className="label">Your expansion rate</span>
            <p className={s.big} aria-live="polite">
              {nf0.format(h0)}
              <span className={s.muted} style={{ fontSize: "var(--text-14)", letterSpacing: 0 }}>
                {" "}
                km/s/Mpc
              </span>
            </p>
            <label className={s.field}>
              <span className="sr-only">Expansion rate</span>
              <input className={s.range} type="range" min={H0_MIN} max={H0_MAX} step={0.5} value={h0} onChange={(e) => set(Number(e.target.value))} aria-valuetext={`${h0} kilometres per second per megaparsec`} />
            </label>
            <p className={s.body}>
              Every megaparsec of distance (3.26 million light-years) adds <strong className="mono">{nf0.format(h0)} km/s</strong> of speed.
              {touched && best !== null && ` The dots sit ${nf0.format(rms)} km/s from your line on average.`}
            </p>
            <div className={s.controls}>
              <Button onClick={() => setShowFit((v) => !v)} aria-pressed={showFit} disabled={best === null}>
                {showFit ? "Hide best fit" : "Show best fit"}
              </Button>
            </div>
            {showFit && best !== null && (
              <dl className={s.readout} aria-live="polite">
                <div>
                  <dt className="label">Best fit</dt>
                  <dd>{best.toFixed(1)}</dd>
                </div>
                <div>
                  <dt className="label">Scatter</dt>
                  <dd>{nf0.format(bestRms)} km/s</dd>
                </div>
              </dl>
            )}
          </div>
          <div className={s.block}>
            <dl className={s.readout}>
              <div className={s.readoutWide}>
                <dt className="label">Age of the universe, roughly</dt>
                <dd>{hubbleTimeGyr(h0).toFixed(1)} billion years</dd>
              </div>
            </dl>
            <p className={s.help}>
              Run the expansion backwards: 1 ÷ H0 is how long ago everything was together, if the speed had never changed. The true age, about
              13.8 billion years, needs the full history of the expansion.
            </p>
          </div>
        </aside>
      </div>

      <section className={s.section} style={{ marginTop: "var(--s-8)" }} aria-labelledby="ex-h">
        <div className={s.sectionHead}>
          <h2 id="ex-h" className={s.h2}>
            Farther means faster, so the universe is expanding
          </h2>
          <p className={s.body}>
            These are type Ia supernovae: exploding white dwarfs that all peak at about the same true brightness, magnitude{" "}
            {String(data?.abs_mag ?? -19.3).replace("-", "−")}. So how faint one looks tells us how far away it is. Its light is also stretched toward red on the way here,
            and that redshift tells us how fast its galaxy is moving away: speed = {nf0.format(C_KMS)} km/s × z.
          </p>
          <p className={s.body}>
            Put them together and the farther a galaxy is, the faster it moves away, in a straight line through zero. Nothing is flying away from
            us in particular: space itself is stretching, so every galaxy moves away from every other, and twice the distance means twice the
            speed. The slope of that line is the Hubble constant, H0. Measurements today give about 67 to 73 km/s/Mpc.
          </p>
        </div>
        <Note icon={<Info size={14} aria-hidden />}>
          Demo data: {pts.length || 30} made-up supernovae, generated in a universe with H0 = 70 and 0.14 mag of scatter.
          Live supernovae from the Transient Name Server replace them later. Speeds use v = cz, which holds for nearby galaxies (z below about
          0.1).
        </Note>
      </section>
    </>
  );
}

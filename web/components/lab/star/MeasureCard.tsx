"use client";

import { useMemo, useState, type CSSProperties } from "react";
import { Info } from "@phosphor-icons/react";
import { Segmented } from "@/components/ui";
import type { KnownPlanet, LabSignal, StarLab, StarLightcurve } from "@/lib/api";
import { linear, Note, nf0, ticks, XAxis, YAxis } from "../chart";
import { useWidth } from "../hooks";
import { foldAndBin, phaseOf } from "../physics";
import { aOverR, grazingInclination, impactParameter, keplerAu, kFromDepth, modelDepth, planetRadius, rmsPpm, transitFlux, type TransitModel } from "../transit";
import { Card } from "./Card";
import { LockedLightcurve, type StarMass } from "./shared";
import s from "./star.module.css";
import l from "../lab.module.css";

const K_MIN = 0.01;
const K_MAX = 0.3;

/** The known planet whose year matches this signal's period, within 1.5%. */
export function matchPlanet(sig: LabSignal, planets: KnownPlanet[]): KnownPlanet | null {
  return planets.find((p) => p.period_d != null && Math.abs(p.period_d / sig.period_d - 1) < 0.015) ?? null;
}

const fmtR = (earth: number) => (earth >= 100 ? nf0.format(earth) : earth >= 10 ? earth.toFixed(1) : earth.toFixed(2));

type Pts = { hours: number[]; flux: number[] };

function DipChart({ raw, bins, model, sig, period }: { raw: Pts; bins: Pts; model: TransitModel; sig: LabSignal; period: number }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = w < 520 ? 260 : 320;
  const m = { l: 60, r: 12, t: 28, b: 44 };
  const win = Math.max(3, sig.duration_h * 1.6);
  const depth = sig.depth_ppm * 1e-6;
  const x = linear([-win, win], [m.l, w - m.r]);
  const y = linear([1 - depth * 1.9, 1 + depth * 0.45], [h - m.b, m.t]);
  const path = useMemo(() => {
    const n = 360;
    let d = "";
    for (let i = 0; i <= n; i++) {
      const hr = -win + (2 * win * i) / n;
      d += `${i ? "L" : "M"}${x(hr).toFixed(1)},${y(transitFlux(hr / 24 / period, model)).toFixed(1)}`;
    }
    return d;
  }, [win, x, y, period, model]);
  const [lo, hi] = y.domain;
  return (
    <div ref={ref}>
      <svg className={l.svg} width={w} height={h} role="img" aria-label={`The folded dip, ${(depth * 100).toFixed(2)}% deep, with your model drawn over it: ${(modelDepth(model) * 100).toFixed(2)}% deep.`}>
        <defs>
          <clipPath id="dip-plot">
            <rect x={m.l} y={m.t} width={w - m.l - m.r} height={h - m.t - m.b} />
          </clipPath>
        </defs>
        <XAxis x={x} y={h - m.b} values={ticks(-win, win, w < 520 ? 4 : 6)} format={(v) => `${v > 0 ? "+" : ""}${v}`} title="Hours from mid-transit" />
        <YAxis y={y} x={m.l} values={ticks(lo, hi, 4)} format={(v) => `${(v * 100).toFixed(1)}%`} grid={[m.l, w - m.r]} title="Brightness" />
        <g clipPath="url(#dip-plot)">
          {raw.hours.map((hr, i) => (
            <circle key={`r${i}`} cx={x(hr)} cy={y(raw.flux[i])} r={1.3} fill="var(--ink-faint)" opacity={0.55} />
          ))}
          {bins.hours.map((hr, i) => (
            <circle key={`b${i}`} cx={x(hr)} cy={y(bins.flux[i])} r={2.4} fill="var(--ink)" />
          ))}
          <path d={path} fill="none" stroke="var(--accent)" strokeWidth={2.2} strokeLinejoin="round" />
        </g>
      </svg>
      <ul className={l.legend}>
        <li>
          <span className={l.key} style={{ background: "var(--ink-faint)" }} aria-hidden />
          TESS measurements, folded
        </li>
        <li>
          <span className={l.key} style={{ background: "var(--ink)" }} aria-hidden />
          Averaged
        </li>
        <li>
          <span className={l.keyLine} style={{ borderTopColor: "var(--accent)" }} aria-hidden />
          Your model
        </li>
      </ul>
    </div>
  );
}

function SignalBench({ lab, lc, sig, mass }: { lab: StarLab; lc: StarLightcurve; sig: LabSignal; mass: StarMass }) {
  const R = lab.radius!;
  const P = sig.period_d;
  const aR = aOverR(keplerAu(mass.value, P), R);
  const known = matchPlanet(sig, lab.known_planets);
  const [k, setK] = useState(0.05);
  const [inc, setInc] = useState(90);
  const iMin = Math.max(45, Math.floor(grazingInclination(aR, K_MAX) - 1));
  const model: TransitModel = { k, aR, inclinationDeg: inc };

  const win = Math.max(3, sig.duration_h * 1.6);
  const { raw, bins, phases, fluxes } = useMemo(() => {
    const { time_btjd: t, flux: f } = lc.unfolded;
    const rawH: number[] = [];
    const rawF: number[] = [];
    for (let i = 0; i < t.length; i++) {
      const hr = phaseOf(t[i], P, sig.t0) * P * 24;
      if (Math.abs(hr) <= win) {
        rawH.push(hr);
        rawF.push(f[i]);
      }
    }
    const nBins = Math.min(4000, Math.max(60, Math.round((P * 24) / (sig.duration_h / 12))));
    const b = foldAndBin(t, f, P, sig.t0, nBins);
    const bh: number[] = [];
    const bf: number[] = [];
    b.phase.forEach((ph, i) => {
      const hr = ph * P * 24;
      if (Math.abs(hr) <= win) {
        bh.push(hr);
        bf.push(b.flux[i]);
      }
    });
    return { raw: { hours: rawH, flux: rawF }, bins: { hours: bh, flux: bf }, phases: bh.map((hr) => hr / 24 / P), fluxes: bf };
  }, [lc, P, sig.t0, sig.duration_h, win]);

  const yours = planetRadius(k, R);
  const pipeline = planetRadius(kFromDepth(sig.depth_ppm * 1e-6), R);
  const b = impactParameter(aR, inc);
  const md = modelDepth(model);
  const gap = rmsPpm(phases, fluxes, model);
  const track = (lo: number, hi: number, v: number) =>
    ({ "--track": `linear-gradient(90deg, var(--accent) ${((v - lo) / (hi - lo)) * 100}%, var(--control-border) 0)` }) as CSSProperties;

  return (
    <div className={l.bench}>
      <div className={l.chartBox}>
        <div className={l.chartHead}>
          <h3 className={l.h3}>The dip, every transit stacked</h3>
          <span className={`${l.help} mono`}>
            {P < 2 ? `every ${(P * 24).toFixed(1)} h` : `every ${P.toFixed(2)} d`}
          </span>
        </div>
        <DipChart raw={raw} bins={bins} model={model} sig={sig} period={P} />
      </div>
      <div className={l.side}>
        <div className={l.block}>
          <label className={l.field}>
            <span className={l.fieldHead}>
              <span className="label">Planet size, Rp/R★</span>
              <span className={s.sliderValue}>{k.toFixed(3)}</span>
            </span>
            <input
              className={l.range}
              style={track(K_MIN, K_MAX, k)}
              type="range"
              min={K_MIN}
              max={K_MAX}
              step={0.0005}
              value={k}
              onChange={(e) => setK(Number(e.target.value))}
              aria-valuetext={`Planet ${k.toFixed(3)} of the star's radius`}
            />
          </label>
          <label className={l.field}>
            <span className={l.fieldHead}>
              <span className="label">Orbit tilt</span>
              <span className={s.sliderValue}>
                {inc.toFixed(1)}°{inc >= 89.95 ? ", edge-on" : ""}
              </span>
            </span>
            <input
              className={l.range}
              style={track(iMin, 90, inc)}
              type="range"
              min={iMin}
              max={90}
              step={0.05}
              value={inc}
              onChange={(e) => setInc(Number(e.target.value))}
              aria-valuetext={`Inclination ${inc.toFixed(1)} degrees; the planet crosses ${b.toFixed(2)} star radii from the centre`}
            />
          </label>
          <dl className={l.readout}>
            <div>
              <dt className="label">Model dip</dt>
              <dd>{(md * 100).toFixed(2)}%</dd>
            </div>
            <div>
              <dt className="label">Gap to data</dt>
              <dd>{Number.isFinite(gap) ? `${nf0.format(gap)} ppm` : "n/a"}</dd>
            </div>
            <div className={l.readoutWide}>
              <dt className="label">Crosses the star</dt>
              <dd>{b > 1 + k ? "misses it" : `${b.toFixed(2)} radii from centre`}</dd>
            </div>
          </dl>
          <p className={l.help}>Make the gap to the data as small as you can. Size sets the depth; tilt sets the length and shape.</p>
        </div>
        <div className={l.block}>
          <dl className={s.compare}>
            <div className={s.yours}>
              <dt>Your planet</dt>
              <dd>
                {fmtR(yours.earth)} R⊕<span className={s.valueNote}>{yours.jupiter.toFixed(2)} Jupiters</span>
              </dd>
            </div>
            <div>
              <dt>
                The pipeline
                <span className={s.valueNote}>from the depth it measured</span>
              </dt>
              <dd>
                {fmtR(pipeline.earth)} R⊕<span className={s.valueNote}>{pipeline.jupiter.toFixed(2)} Jupiters</span>
              </dd>
            </div>
            <div>
              <dt>
                NASA archive
                <span className={s.valueNote}>{known ? known.name : "no known planet at this period"}</span>
              </dt>
              <dd>
                {known?.radius != null ? (
                  <>
                    {fmtR(known.radius)} R⊕<span className={s.valueNote}>{(known.radius / 11.209).toFixed(2)} Jupiters</span>
                  </>
                ) : known ? (
                  "not listed"
                ) : (
                  "n/a"
                )}
              </dd>
            </div>
          </dl>
          <p className={l.help}>
            Sizes use {lab.name}&apos;s radius, <span className="mono">{R.toFixed(2)} R☉</span>, and an orbit of{" "}
            <span className="mono">{aR.toFixed(1)}</span> star radii from Kepler&apos;s law ({mass.estimated ? "mass estimated from temperature" : "catalogued mass"}).
          </p>
        </div>
      </div>
    </div>
  );
}

export function MeasureCard({ lab, lc, standIn, mass, lcError }: { lab: StarLab; lc: StarLightcurve | null; standIn: string | null; mass: StarMass | null; lcError: string | null }) {
  const [pick, setPick] = useState("0");
  const lede = "Fit a planet to the dip: slide its size and the tilt of its orbit until the model lies on the data, then compare your answer.";
  if (!lab.lightcurve.available) {
    return (
      <Card id="measure" title="Measure its planet" lede={lede} locked={<LockedLightcurve lab={lab} />}>
        {lab.lightcurve.reason_if_not === "not_analyzed" && (
          <a className={l.linkQuiet} href="#hear">
            Analyze it in Hear it, above
          </a>
        )}
      </Card>
    );
  }
  if (!lab.signals.length) {
    return <Card id="measure" title="Measure its planet" lede={lede} locked="The analysis found no repeating dip in its light curve, so there is no transit to measure." />;
  }
  if (!lab.radius) {
    return <Card id="measure" title="Measure its planet" lede={lede} locked="No radius is listed for this star, so a planet's share of it can't be turned into a size." />;
  }
  if (!mass) {
    return <Card id="measure" title="Measure its planet" lede={lede} locked="No mass or temperature is listed for this star, so its planet's orbit, and so the dip's shape, can't be modelled." />;
  }
  const i = Math.min(Number(pick), lab.signals.length - 1);
  const sig = lab.signals[i];
  return (
    <Card id="measure" title="Measure its planet" data={standIn ? "demo" : "real"} lede={lede}>
      {standIn && (
        <p className={l.help}>
          Demo: {standIn}&apos;s light curve and signal stand in until the analysis service is connected. Sizes use {lab.name}&apos;s own radius, so
          this is not a result for {lab.name}.
        </p>
      )}
      {lab.signals.length > 1 && (
        <div>
          <Segmented
            label="Signal"
            value={String(i)}
            onChange={setPick}
            options={lab.signals.map((g, n) => ({ value: String(n), label: matchPlanet(g, lab.known_planets)?.name ?? `Signal ${n + 1}, ${g.period_d.toFixed(2)} d` }))}
          />
        </div>
      )}
      {lcError ? (
        <p className={l.help} role="alert">
          The light curve didn&apos;t load: {lcError}
        </p>
      ) : lc ? (
        <SignalBench key={i} lab={lab} lc={lc} sig={sig} mass={mass} />
      ) : (
        <div className={l.skeleton} aria-busy="true" role="status">
          <span className="sr-only">Loading the light curve</span>
        </div>
      )}
      <div className={s.explain}>
        <p className={l.body}>
          When the planet crosses, it hides a small disk of the star. The share of light lost is the share of the star&apos;s face it covers,
          <strong> (Rp/R★)²</strong>, so the depth gives the size. A planet crossing the middle makes a long, flat-bottomed dip; tilt the orbit and it
          crosses nearer the edge, so the dip gets shorter and more V-shaped, until it misses the star entirely.
        </p>
        <Note icon={<Info size={14} aria-hidden />}>
          A simple model: the star is drawn as an evenly bright disk and the orbit as a circle. Real stars are darker toward their edges, so real
          dips have rounder bottoms than this model. The pipeline&apos;s size is √depth × the star&apos;s radius; NASA&apos;s comes from published fits.
          1 Jupiter = 11.2 Earth radii.
        </Note>
      </div>
    </Card>
  );
}

"use client";

import { Drawer } from "@/components/picture/Drawer";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties, type PointerEvent } from "react";
import { ArrowRight, Info } from "@phosphor-icons/react";
import { Button, Tag } from "@/components/ui";
import { linear, log, LoadError, Note, nf0, Skeleton, XAxis, YAxis } from "./chart";
import { useWidth } from "./hooks";
import { blackbodyCurve, blueRedRatio, rgbCss, SUN_TEFF, surfaceBrightnessVsSun, temperatureColor, wavelengthRgb, wienPeakNm } from "./physics";
import { FAMOUS, loadLabStars, type LabStar } from "./stars";
import s from "./lab.module.css";

const T_MIN = 2000;
const T_MAX = 40000;
const STEPS = 1000;
const toT = (v: number) => Math.round((T_MIN * (T_MAX / T_MIN) ** (v / STEPS)) / 10) * 10;
const toV = (t: number) => Math.round((STEPS * Math.log(t / T_MIN)) / Math.log(T_MAX / T_MIN));

const PRESETS = [
  { label: "Red dwarf", t: 3000 },
  { label: "Sun", t: SUN_TEFF },
  { label: "Sirius", t: 9940 },
  { label: "Hot blue star", t: 30000 },
];

/** Where the peak falls, in words. */
export function peakWords(nm: number): string {
  if (nm < 380) return "in the ultraviolet, beyond violet: invisible to us";
  if (nm < 450) return "in violet light";
  if (nm < 495) return "in blue light";
  if (nm < 570) return "in green light";
  if (nm < 590) return "in yellow light";
  if (nm < 620) return "in orange light";
  if (nm < 750) return "in red light";
  return "in the infrared, beyond red: invisible to us";
}

export function colourWords(teff: number): string {
  if (teff < 3700) return "orange-red";
  if (teff < 5200) return "orange";
  if (teff < 6000) return "yellow-white";
  if (teff < 7500) return "white";
  if (teff < 10000) return "blue-white";
  return "blue";
}

const RAINBOW = Array.from({ length: 19 }, (_, i) => 380 + i * 20);

// ---------- the spectrum chart ----------

export function SpectrumChart({ teff }: { teff: number }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = w < 520 ? 240 : 300;
  const m = { l: 40, r: 12, t: 28, b: 44 };
  const x = linear([0, 2500], [m.l, w - m.r]);
  const y = linear([0, 1.08], [h - m.b, m.t]);
  const curve = useMemo(() => blackbodyCurve(teff, 1, 2500, 360), [teff]);
  const sun = useMemo(() => blackbodyCurve(SUN_TEFF, 1, 2500, 360), []);
  const path = (c: { nm: number[]; value: number[] }) => c.nm.map((n, i) => `${i ? "L" : "M"}${x(n).toFixed(1)},${y(c.value[i]).toFixed(1)}`).join("");
  const peak = wienPeakNm(teff);
  const colour = rgbCss(temperatureColor(teff));
  const peakX = x(Math.min(peak, 2500));
  const labelRight = peakX < w - 150;
  return (
    <div ref={ref}>
      <svg className={s.svg} width={w} height={h} role="img" aria-label={`Blackbody curve for ${nf0.format(teff)} K. It peaks at ${nf0.format(peak)} nanometres, ${peakWords(peak)}.`}>
        <defs>
          <linearGradient id="rainbow" x1={x(380)} x2={x(750)} y1="0" y2="0" gradientUnits="userSpaceOnUse">
            {RAINBOW.map((nm) => (
              <stop key={nm} offset={(nm - 380) / 370} stopColor={rgbCss(wavelengthRgb(nm))} />
            ))}
          </linearGradient>
          <clipPath id="under">
            <path d={`${path(curve)}L${x(2500)},${y(0)}L${x(1)},${y(0)}Z`} />
          </clipPath>
        </defs>
        <rect x={x(380)} y={m.t} width={x(750) - x(380)} height={h - m.b - m.t} fill="url(#rainbow)" opacity={0.1} />
        <rect x={x(380)} y={m.t} width={x(750) - x(380)} height={h - m.b - m.t} fill="url(#rainbow)" opacity={0.85} clipPath="url(#under)" />
        <text className={s.axisTitle} x={x(190)} y={m.t - 10} textAnchor="middle">
          UV
        </text>
        <text className={s.axisTitle} x={x(565)} y={m.t - 10} textAnchor="middle">
          Visible
        </text>
        <text className={s.axisTitle} x={x(1600)} y={m.t - 10} textAnchor="middle">
          Infrared
        </text>
        <XAxis x={x} y={h - m.b} values={[0, 500, 1000, 1500, 2000, 2500]} format={(v) => nf0.format(v)} title="Wavelength, nm" />
        <YAxis y={y} x={m.l} values={[0, 0.5, 1]} format={(v) => (v === 1 ? "peak" : v === 0 ? "0" : "½")} grid={[m.l, w - m.r]} />
        <path d={path(sun)} fill="none" stroke="var(--ink-muted)" strokeWidth={1.25} strokeDasharray="4 4" />
        <path d={path(curve)} fill="none" stroke={colour} strokeWidth={2.4} />
        {peak <= 2500 && (
          <g>
            <line x1={peakX} x2={peakX} y1={y(1)} y2={h - m.b} stroke="var(--ink)" strokeWidth={1} strokeDasharray="2 3" />
            <circle cx={peakX} cy={y(1)} r={4.5} fill={colour} stroke="var(--bg-deep)" strokeWidth={2} />
            <text className={s.chartLabelStrong} x={labelRight ? peakX + 10 : peakX - 10} y={y(1) + 4} textAnchor={labelRight ? "start" : "end"}>
              Peak {nf0.format(peak)} nm
            </text>
          </g>
        )}
      </svg>
      <ul className={s.legend}>
        <li>
          <span className={s.keyLine} style={{ borderTopColor: colour }} aria-hidden />
          This star, {nf0.format(teff)} K
        </li>
        <li>
          <span className={`${s.keyLine} ${s.keyDash}`} aria-hidden />
          The Sun, {nf0.format(SUN_TEFF)} K
        </li>
        <li>Each curve is scaled to its own peak</li>
      </ul>
    </div>
  );
}

// ---------- the star field: temperature vs brightness ----------

const L_MIN = 1e-4;
const L_MAX = 1e6;

export function StarField({ stars, teff, picked, onPick, labelPicked }: { stars: LabStar[]; teff: number; picked: LabStar | null; onPick: (st: LabStar) => void; labelPicked?: boolean }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const canvas = useRef<HTMLCanvasElement>(null);
  const h = w < 520 ? 300 : 380;
  const m = { l: 68, r: 12, t: 28, b: 44 };
  const x = useMemo(() => log([T_MIN, T_MAX], [m.l, w - m.r]), [w, m.l, m.r]);
  const y = useMemo(() => log([L_MIN, L_MAX], [h - m.b, m.t]), [h, m.b, m.t]);
  const [hover, setHover] = useState<LabStar | null>(null);
  const shown = useMemo(() => stars.filter((st) => st.teff >= T_MIN && st.teff <= T_MAX && st.lum >= L_MIN && st.lum <= L_MAX), [stars]);

  useEffect(() => {
    const c = canvas.current;
    if (!c) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    c.width = w * dpr;
    c.height = h * dpr;
    const g = c.getContext("2d");
    if (!g) return;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    for (const st of shown) {
      g.fillStyle = rgbCss(temperatureColor(st.teff));
      g.globalAlpha = st.kind === "host" ? 0.95 : 0.7;
      g.beginPath();
      g.arc(x(st.teff), y(st.lum), st.kind === "host" ? 2 : 1.6, 0, Math.PI * 2);
      g.fill();
    }
    g.globalAlpha = 1;
  }, [shown, w, h, x, y]);

  const nearest = useCallback(
    (px: number, py: number) => {
      let best: LabStar | null = null;
      let bd = 144; // 12 px
      for (const st of shown) {
        const d = (x(st.teff) - px) ** 2 + (y(st.lum) - py) ** 2;
        if (d < bd) {
          bd = d;
          best = st;
        }
      }
      return best;
    },
    [shown, x, y],
  );

  const at = (e: PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return nearest(e.clientX - r.left, e.clientY - r.top);
  };

  const mark = (st: LabStar | null, strong: boolean) =>
    st && (
      <circle cx={x(st.teff)} cy={y(st.lum)} r={strong ? 7 : 6} fill="none" stroke={strong ? "var(--accent)" : "var(--ink)"} strokeWidth={strong ? 2 : 1.25} />
    );
  const tx = x(teff);
  const sunX = x(SUN_TEFF);
  const sunY = y(1);
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <canvas
        ref={canvas}
        className={s.canvas}
        style={{ height: h }}
        aria-hidden
        onPointerMove={(e) => e.pointerType === "mouse" && setHover(at(e))}
        onPointerLeave={() => setHover(null)}
        onClick={(e) => {
          const st = at(e as unknown as PointerEvent);
          if (st) onPick(st);
        }}
      />
      <svg className={s.svg} width={w} height={h} style={{ position: "absolute", inset: 0, pointerEvents: "none" }} aria-hidden>
        <XAxis x={x} y={h - m.b} values={w < 520 ? [2000, 5000, 10000, 20000, 40000] : [2000, 3000, 5000, 10000, 20000, 40000]} format={(v) => `${nf0.format(v)}`} title="Temperature, K" />
        <YAxis y={y} x={m.l} values={[1e-4, 1e-2, 1, 100, 1e4, 1e6]} format={(v) => (v >= 1 ? nf0.format(v) : String(v))} grid={[m.l, w - m.r]} title="Light given off, Suns" />
        <line x1={tx} x2={tx} y1={m.t} y2={h - m.b} stroke="var(--ink)" strokeWidth={1} strokeDasharray="2 3" />
        <circle cx={sunX} cy={sunY} r={5} fill="none" stroke="var(--ink)" strokeWidth={1.5} />
        <circle cx={sunX} cy={sunY} r={1.5} fill="var(--ink)" />
        <text className={s.chartLabel} x={sunX + 9} y={sunY + 4}>
          Sun
        </text>
        {mark(hover, false)}
        {mark(picked, true)}
        {labelPicked && picked && (
          <text className={s.chartLabelStrong} x={x(picked.teff) + (x(picked.teff) > w - 160 ? -12 : 12)} y={y(picked.lum) - 10} textAnchor={x(picked.teff) > w - 160 ? "end" : "start"} style={{ paintOrder: "stroke", stroke: "var(--bg-deep)", strokeWidth: 5, strokeLinejoin: "round" }}>
            {picked.name}
          </text>
        )}
      </svg>
      {hover && (
        <div className={s.tooltip} style={{ left: x(hover.teff), top: y(hover.lum) }}>
          {hover.name} <span className="mono">{nf0.format(hover.teff)} K</span>
        </div>
      )}
    </div>
  );
}

// ---------- the page ----------

export function Thermometer() {
  const [teff, setTeff] = useState(SUN_TEFF);
  const [stars, setStars] = useState<LabStar[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [picked, setPicked] = useState<LabStar | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    loadLabStars(ctl.signal)
      .then(setStars)
      .catch((e: unknown) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)));
    return () => ctl.abort();
  }, [attempt]);

  const famous = useMemo(() => (stars ? FAMOUS.map((n) => stars.find((st) => st.name === n)).filter((st): st is LabStar => !!st) : []), [stars]);
  const pick = (st: LabStar) => {
    setPicked(st);
    setTeff(Math.min(T_MAX, Math.max(T_MIN, st.teff)));
  };

  const colour = temperatureColor(teff);
  const peak = wienPeakNm(teff);
  const ratio = blueRedRatio(teff);
  const track = useMemo(
    () => `linear-gradient(90deg, ${Array.from({ length: 12 }, (_, i) => rgbCss(temperatureColor(toT((i / 11) * STEPS)))).join(", ")})`,
    [],
  );

  return (
    <>
      <div className={s.bench}>
        <div className={s.stage}>
          <section className={s.chartBox} aria-labelledby="spec-h">
            <div className={s.chartHead}>
              <h2 id="spec-h" className={s.h3}>
                Light given off at each wavelength
              </h2>
            </div>
            <SpectrumChart teff={teff} />
          </section>
        </div>

        <aside className={s.side} aria-label="Temperature">
          <div className={s.block}>
            <div className={s.swatchRow}>
              <span className={s.swatch} style={{ background: rgbCss(colour) }} aria-hidden />
              <div>
                <p className={s.big}>{nf0.format(teff)} K</p>
                <p className={s.muted}>Looks {colourWords(teff)}</p>
              </div>
            </div>
            <label className={s.field}>
              <span className={s.fieldHead}>
                <span className="label">Surface temperature</span>
              </span>
              <input
                className={s.range}
                style={{ "--track": track } as CSSProperties}
                type="range"
                min={0}
                max={STEPS}
                value={toV(teff)}
                onChange={(e) => {
                  setTeff(toT(Number(e.target.value)));
                  setPicked(null);
                }}
                aria-valuetext={`${nf0.format(teff)} kelvin`}
              />
              <span className={`${s.scaleLabels} mono ${s.help}`}>
                <span>2,000 K</span>
                <span>40,000 K</span>
              </span>
            </label>
            <div className={s.controls}>
              {PRESETS.map((p) => (
                <Button
                  key={p.label}
                  size="sm"
                  aria-pressed={teff === p.t}
                  onClick={() => {
                    setTeff(p.t);
                    setPicked(null);
                  }}
                >
                  {p.label}
                </Button>
              ))}
            </div>
          </div>

          <div className={s.block}>
            <dl className={s.readout}>
              <div>
                <dt className="label">Brightest at</dt>
                <dd>{nf0.format(peak)} nm</dd>
              </div>
              <div>
                <dt className="label">Blue vs red</dt>
                <dd>{ratio >= 1 ? `${ratio.toFixed(1)}× bluer` : `${(1 / ratio).toFixed(1)}× redder`}</dd>
              </div>
              <div className={s.readoutWide}>
                <dt className="label">Light per square metre</dt>
                <dd>{(() => { const v = surfaceBrightnessVsSun(teff); return v >= 10 ? nf0.format(v) : v.toFixed(2); })()}× the Sun</dd>
              </div>
            </dl>
            <p className={s.body}>
              Wien&apos;s law: the peak wavelength is <strong>2,898,000 ÷ temperature</strong> (in nm and kelvin). At {nf0.format(teff)} K
              that is {nf0.format(peak)} nm, {peakWords(peak)}.
            </p>
          </div>
        </aside>
      </div>

      <div className={s.bench} style={{ marginTop: "var(--s-8)" }}>
        <section className={s.chartBox} aria-labelledby="field-h">
          <div className={s.chartHead}>
            <h2 id="field-h" className={s.h3}>
              Real stars on the same colour scale
            </h2>
            {stars && <span className={`${s.help} mono`}>{nf0.format(stars.length)} stars</span>}
          </div>
          {error ? (
            <LoadError
              what="The star catalogues"
              error={error}
              onRetry={() => {
                setError(null);
                setAttempt((n) => n + 1);
              }}
            />
          ) : stars ? (
            <StarField stars={stars} teff={teff} picked={picked} onPick={pick} />
          ) : (
            <Skeleton label="Loading the stars" />
          )}
          <p className={s.help} style={{ padding: "var(--s-2) var(--s-1) 0" }}>
            Click a dot to pick a star. Brighter dots are planet hosts. Hot stars to the right, cool to the left.
          </p>
        </section>

        <aside className={s.side} aria-label="Pick a star">
          {picked ? (
            <div className={s.picked} aria-live="polite">
              <div className={s.rowBetween}>
                <p className={s.h3}>{picked.name}</p>
                <Tag>{picked.kind === "host" ? "Planet host" : "Star"}</Tag>
              </div>
              <p className={s.body}>
                <span className="mono">{nf0.format(picked.teff)} K</span>
                {picked.teffEstimated ? ", estimated from its colour (B−V)" : ", TESS Input Catalog"}. Gives off{" "}
                <span className="mono">{picked.lum >= 10 ? nf0.format(picked.lum) : picked.lum.toPrecision(2)}×</span> the Sun&apos;s visible light.
                {picked.planets.length > 0 && ` Known planets: ${picked.planets.join(", ")}.`}
              </p>
              <Link className={s.linkButton} href={picked.href}>
                See it on the sky
                <ArrowRight size={14} aria-hidden />
              </Link>
            </div>
          ) : (
            <p className={s.body}>Pick a dot, or one of these well-known stars, to set the thermometer to its temperature.</p>
          )}
          <ul className={s.starList} aria-label="Well-known stars">
            {famous.map((st) => (
              <li key={`${st.kind}${st.i}`}>
                <button className={s.starButton} aria-current={picked === st} onClick={() => pick(st)}>
                  <span className={s.key} style={{ background: rgbCss(temperatureColor(st.teff)) }} aria-hidden />
                  <span>{st.name}</span>
                  <span className={`mono ${s.muted}`}>{nf0.format(st.teff)} K</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>
      </div>

      <div style={{ marginTop: "var(--s-16)" }}>
        <Drawer title="Why colour is heat" state="Explanation">
        <div className={s.sectionHead}>
          <p className={s.body}>
            Anything hot glows, and a star glows at every colour at once, just not equally. Its light piles up around one wavelength, the peak. Heat
            the star and the peak slides toward shorter wavelengths, toward blue. Twice as hot means half the wavelength.
          </p>
          <p className={s.body}>
            A 3,000 K red dwarf peaks in the infrared, so the light we can see comes mostly from its red side. A 30,000 K star peaks in the
            ultraviolet, so its visible light leans blue. The Sun peaks in blue-green, but it pours out red and blue too, and the mix looks white.
            That is also why there are no green stars: a green peak always comes with plenty of red and blue.
          </p>
        </div>
        <Note icon={<Info size={14} aria-hidden />}>
          Dots use the same blackbody colours as the sky, with its one saturation boost so colour reads on black. Temperatures come from the
          TESS Input Catalog for planet hosts and are estimated from colour (B−V) for bright stars. Brightness is visible light only, from each
          star&apos;s magnitude and distance.
        </Note>
        </Drawer>
      </div>
    </>
  );
}

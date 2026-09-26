"use client";

import { useEffect, useMemo, useState, type PointerEvent } from "react";
import { useSearchParams } from "next/navigation";
import { Info } from "@phosphor-icons/react";
import { DemoTag, EmptyState, Segmented, Tag } from "@/components/ui";
import { linear, log, Note, nf0, Skeleton, ticks, XAxis, YAxis } from "./chart";
import { useWidth } from "./hooks";
import { rgbCss, wavelengthRgb } from "./physics";
import {
  abundancesPath,
  atmospherePath,
  elementName,
  elementsPath,
  formatTimesSun,
  gaiaXpPath,
  loadSpectra,
  planetSlug,
  speciesName,
  sunPath,
  telluricSpecies,
  type Abundances,
  type Atmosphere,
  type ElementLines,
  type GaiaXp,
  type Loaded,
  type SunSpectrum,
} from "./spectra";
import s from "./lab.module.css";

const VIS: [number, number] = [380, 750];
const RAINBOW = Array.from({ length: 38 }, (_, i) => 380 + i * 10);

/** Stars and planets the Lab looks for. The SPECTRA session's files are read by these names. */
export const LAB_STARS = [
  { tic: 100100827, name: "WASP-18" },
  { tic: 22529346, name: "WASP-121" },
  { tic: 181949561, name: "WASP-39" },
];
export const LAB_PLANETS = ["WASP-121 b", "WASP-39 b", "WASP-18 b"];

/** "H2O" as "H₂O". */
export function formula(species: string): string {
  return species.replace(/\d/g, (d) => "₀₁₂₃₄₅₆₇₈₉"[Number(d)]);
}

export function useSpectra<T>(path: string | null) {
  const [state, setState] = useState<{ path: string | null; value: Loaded<T> | null; done: boolean }>({ path: null, value: null, done: false });
  useEffect(() => {
    if (!path) return;
    const ctl = new AbortController();
    loadSpectra<T>(path, ctl.signal)
      .then((value) => setState({ path, value, done: true }))
      .catch(() => {});
    return () => ctl.abort();
  }, [path]);
  const fresh = state.path === path;
  return { value: fresh ? state.value : null, loading: !fresh || !state.done };
}

export function SourceLine({ demo, text }: { demo: boolean; text: string }) {
  return (
    <p className={s.help}>
      {demo && (
        <>
          <DemoTag />{" "}
        </>
      )}
      {demo ? text.replace(/^DEMO:\s*/, "").replace(/^Demo data;\s*/, "").replace(/^./, (c) => c.toUpperCase()) : text}
    </p>
  );
}

// ---------- (a) barcode lab ----------

function Barcode({ lines, mode, mix, label }: { lines: { nm: number; relative_intensity: number }[]; mode: "emission" | "absorption"; mix?: boolean; label: string }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const x = linear(VIS, [0, w]);
  const h = mix ? 56 : 36;
  const id = `rb-${mix ? "mix" : label}`;
  return (
    <div ref={ref}>
      <svg className={`${s.barcode} ${mix ? s.barcodeMix : ""}`} width={w} height={h} role="img" aria-label={label}>
        <defs>
          <linearGradient id={id} x1="0" x2={w} y1="0" y2="0" gradientUnits="userSpaceOnUse">
            {RAINBOW.map((nm) => (
              <stop key={nm} offset={(nm - 380) / 370} stopColor={rgbCss(wavelengthRgb(nm))} />
            ))}
          </linearGradient>
        </defs>
        <rect width={w} height={h} fill={mode === "emission" ? "var(--space)" : `url(#${id})`} />
        {lines
          .filter((l) => l.nm >= VIS[0] && l.nm <= VIS[1])
          .map((l, i) => (
            <rect
              key={`${l.nm}-${i}`}
              x={x(l.nm) - 1.25}
              width={2.5}
              height={h}
              fill={mode === "emission" ? rgbCss(wavelengthRgb(l.nm)) : "var(--space)"}
              opacity={0.35 + 0.65 * Math.min(1, l.relative_intensity)}
            />
          ))}
      </svg>
    </div>
  );
}

function BarcodeLab() {
  const { value, loading } = useSpectra<ElementLines[]>(elementsPath);
  const [on, setOn] = useState<string[]>(["H", "Na"]);
  const [mode, setMode] = useState<"emission" | "absorption">("emission");
  const els = value?.data ?? [];
  const chosen = els.filter((e) => on.includes(e.symbol));
  const mix = chosen.flatMap((e) => e.lines);
  const [axRef, aw] = useWidth<HTMLDivElement>();
  const ax = linear(VIS, [0, aw]);
  return (
    <section className={s.section} aria-labelledby="bar-h">
      <div className={s.sectionHead}>
        <div className={s.titleRow}>
          <h2 id="bar-h" className={s.h2}>
            Element barcodes
          </h2>
          {value?.demo && <DemoTag />}
        </div>
        <p className={s.body}>
          Every element glows and absorbs at its own exact colours, a pattern as unique as a barcode. Switch elements on to see their lines, and
          look at the bottom row to see the mix: that is how astronomers read what a star is made of.
        </p>
      </div>
      {loading ? (
        <Skeleton label="Loading element lines" />
      ) : !value ? (
        <EmptyState title="No element lines yet">The line list arrives with the spectra data.</EmptyState>
      ) : (
        <>
          <div className={s.rowBetween} style={{ flexWrap: "wrap" }}>
            <div className={s.chips} role="group" aria-label="Elements">
              {els.map((e) => (
                <button
                  key={e.symbol}
                  className={s.chip}
                  aria-pressed={on.includes(e.symbol)}
                  onClick={() => setOn((cur) => (cur.includes(e.symbol) ? cur.filter((x) => x !== e.symbol) : [...cur, e.symbol]))}
                >
                  <b>{e.symbol}</b>
                  {e.name}
                </button>
              ))}
            </div>
            <Segmented
              label="Light"
              value={mode}
              onChange={setMode}
              options={[
                { value: "emission", label: "Glowing gas" },
                { value: "absorption", label: "Starlight through gas" },
              ]}
            />
          </div>
          <div className={s.chartBox}>
            <div className={s.barcodes}>
              {chosen.map((e) => {
                const hidden = e.lines.filter((l) => l.nm < VIS[0] || l.nm > VIS[1]).length;
                return (
                  <div key={e.symbol} className={s.barcodeRow}>
                    <span className={s.barcodeName}>
                      <b>{e.symbol}</b>
                      <span>{hidden ? `+${hidden} unseen` : e.name}</span>
                    </span>
                    <Barcode lines={e.lines} mode={mode} label={`${e.name}: ${e.lines.length} lines`} />
                  </div>
                );
              })}
              <div className={s.barcodeRow} style={{ marginTop: "var(--s-2)" }}>
                <span className={s.barcodeName}>
                  <b>Mix</b>
                  <span>{chosen.length ? chosen.map((e) => e.symbol).join(" + ") : "nothing yet"}</span>
                </span>
                <Barcode lines={mix} mode={mode} mix label={`Combined lines of ${chosen.map((e) => e.name).join(", ") || "no elements"}`} />
              </div>
              <div className={s.barcodeRow}>
                <span />
                <div ref={axRef} aria-hidden>
                  <svg className={s.svg} width={aw} height={20}>
                    {[400, 450, 500, 550, 600, 650, 700, 750].map((v) => (
                      <text key={v} className={s.axis} x={Math.min(aw - 14, Math.max(14, ax(v)))} y={14} textAnchor="middle">
                        {v}
                      </text>
                    ))}
                  </svg>
                </div>
              </div>
            </div>
          </div>
          <p className={s.help}>
            Wavelength in nanometres, violet to red. &quot;Unseen&quot; lines fall in the infrared or ultraviolet, outside this strip. Line positions
            are laboratory wavelengths.
          </p>
        </>
      )}
    </section>
  );
}

// ---------- (b) the Sun ----------

function SunChart({ sun }: { sun: SunSpectrum }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const narrow = w < 560;
  const h = narrow ? 240 : 300;
  const m = { l: 44, r: 12, t: 64, b: 44 };
  const x = linear([sun.wavelength_nm[0], sun.wavelength_nm.at(-1)!], [m.l, w - m.r]);
  const maxF = Math.max(...sun.flux);
  const y = linear([0, maxF * 1.05], [h - m.b, m.t]);
  const [hover, setHover] = useState<SunSpectrum["lines"][number] | null>(null);
  const d = useMemo(() => {
    const step = Math.max(1, Math.floor(sun.flux.length / (w * 1.5)));
    let out = "";
    for (let i = 0; i < sun.flux.length; i += step) out += `${out ? "L" : "M"}${x(sun.wavelength_nm[i]).toFixed(1)},${y(sun.flux[i]).toFixed(1)}`;
    return out;
  }, [sun, w, x, y]);

  // The strip above the chart: each wavelength in its colour, as bright as the Sun is there.
  const strip = useMemo(() => {
    const n = Math.min(400, Math.floor(w - m.l - m.r));
    return Array.from({ length: n }, (_, k) => {
      const nm = x.invert(m.l + ((k + 0.5) * (w - m.l - m.r)) / n);
      const i = Math.min(sun.flux.length - 1, Math.max(0, sun.wavelength_nm.findIndex((v) => v >= nm)));
      const c = wavelengthRgb(nm);
      const b = Math.min(1, (sun.flux[i] / maxF) * 1.15);
      return { k, c: rgbCss([c[0] * b, c[1] * b, c[2] * b]) };
    });
  }, [sun, w, x, maxF, m.l, m.r]);
  const cellW = (w - m.l - m.r) / strip.length;

  const onMove = (e: PointerEvent<SVGSVGElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    const nm = x.invert(e.clientX - r.left);
    let best: SunSpectrum["lines"][number] | null = null;
    let bd = narrow ? 6 : 3.5;
    for (const l of sun.lines) {
      const dd = Math.abs(l.nm - nm);
      if (dd < bd) {
        bd = dd;
        best = l;
      }
    }
    setHover(best);
  };

  const solar = sun.lines.filter((l) => !telluricSpecies(l));
  const earth = sun.lines.filter((l) => telluricSpecies(l));
  const labelled = solar.filter((l, i, a) => i === 0 || Math.abs(x(l.nm) - x(a[i - 1].nm)) > (narrow ? 22 : 16));
  /** Where a line's dip bottoms out, so an Earth's-air label can sit just under it. */
  const dipY = (nm: number) => {
    let min = Infinity;
    sun.wavelength_nm.forEach((v, i) => {
      if (Math.abs(v - nm) <= 3 && sun.flux[i] < min) min = sun.flux[i];
    });
    return y(Number.isFinite(min) ? min : maxF);
  };
  const hoverEarth = hover ? telluricSpecies(hover) : null;
  const solarNames = [...new Set(solar.map((l) => elementName(l.element)))];
  return (
    <div ref={ref} style={{ position: "relative" }}>
      <svg
        className={s.svg}
        width={w}
        height={h}
        role="img"
        aria-label={`The Sun's spectrum from ${sun.wavelength_nm[0]} to ${sun.wavelength_nm.at(-1)} nm, with dark lines from ${solarNames.join(", ")}${earth.length ? `, plus ${earth.length} lines from oxygen or water in Earth's air` : ""}.`}
        onPointerMove={onMove}
        onPointerDown={onMove}
        onPointerLeave={() => setHover(null)}
      >
        {strip.map((c) => (
          <rect key={c.k} x={m.l + c.k * cellW} y={m.t - 44} width={cellW + 0.6} height={22} fill={c.c} />
        ))}
        <XAxis x={x} y={h - m.b} values={ticks(x.domain[0], x.domain[1], narrow ? 4 : 8)} format={(v) => nf0.format(v)} title="Wavelength, nm" />
        <YAxis y={y} x={m.l} values={[0, 0.5, 1]} format={(v) => (v === 0 ? "0" : v === 1 ? "1" : "½")} grid={[m.l, w - m.r]} />
        <path d={d} fill="none" stroke="var(--ink-secondary)" strokeWidth={1.25} />
        {labelled.map((l) => (
          <text key={l.nm} className={s.axis} x={x(l.nm)} y={m.t - 8} textAnchor="middle" style={{ fill: hover?.nm === l.nm ? "var(--ink)" : undefined }}>
            {l.element}
          </text>
        ))}
        {/* Earth's air: dashed guide and a label under the dip, never in the row of solar elements. */}
        {earth.map((l, i) => {
          const sp = telluricSpecies(l)!;
          const lx = x(l.nm);
          const ly = Math.min(h - m.b - 6, dipY(l.nm) + 16 + (narrow && i % 2 ? 14 : 0));
          const anchor = lx > w - m.r - 60 ? "end" : lx < m.l + 60 ? "start" : "middle";
          return (
            <g key={l.nm} className={s.telluric} data-active={hover?.nm === l.nm}>
              <line x1={lx} x2={lx} y1={m.t - 22} y2={ly - 12} strokeDasharray="2 3" />
              <text x={lx} y={ly} textAnchor={anchor}>
                {sp === "O2" ? "O₂" : "H₂O"}: Earth&apos;s air
              </text>
            </g>
          );
        })}
        {hover && <line x1={x(hover.nm)} x2={x(hover.nm)} y1={m.t - 44} y2={h - m.b} stroke="var(--accent)" strokeWidth={1.5} />}
      </svg>
      {hover && (
        <div className={s.tooltip} style={{ left: x(hover.nm), top: m.t - 44 }}>
          {hoverEarth ? (
            <>
              {hoverEarth === "O2" ? "Oxygen (O₂)" : "Water vapour (H₂O)"} in Earth&apos;s air, not the Sun{hover.label ? ` (${hover.label})` : ""}
            </>
          ) : (
            <>
              {elementName(hover.element)[0].toUpperCase() + elementName(hover.element).slice(1)}
              {hover.label ? ` (${hover.label})` : ""}
            </>
          )}{" "}
          <span className="mono">{hover.nm.toFixed(1)} nm</span>
        </div>
      )}
      <ul className={s.legend} style={{ paddingTop: "var(--s-2)" }}>
        <li>Letters above the strip: elements in the Sun</li>
        {earth.length > 0 && (
          <li>
            <span className={`${s.keyLine} ${s.keyDash}`} aria-hidden />
            Dashed: absorbed by Earth&apos;s air on the way to the telescope
          </li>
        )}
      </ul>
    </div>
  );
}

const COUNT = ["No", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine"];

function SunSection() {
  const { value, loading } = useSpectra<SunSpectrum>(sunPath);
  const earthCount = value ? value.data.lines.filter((l) => telluricSpecies(l)).length : 0;
  return (
    <section className={s.section} aria-labelledby="sun-h">
      <div className={s.sectionHead}>
        <div className={s.titleRow}>
          <h2 id="sun-h" className={s.h2}>
            The Sun&apos;s barcode
          </h2>
          {value?.demo && <DemoTag />}
        </div>
        <p className={s.body}>
          Spread sunlight into a rainbow and it is crossed by dark lines: colours taken out by atoms in the Sun&apos;s outer layers. Point at a dip
          to see which element made it.
          {value && earthCount > 0 && (
            <>
              {" "}
              <strong>
                {COUNT[earthCount] ?? earthCount} of these dark {earthCount === 1 ? "lines comes" : "lines come"} from Earth&apos;s own air, not the Sun.
              </strong>
            </>
          )}
        </p>
      </div>
      {loading ? (
        <Skeleton label="Loading the solar spectrum" />
      ) : !value ? (
        <EmptyState title="No solar spectrum yet">It arrives with the spectra data.</EmptyState>
      ) : (
        <>
          <div className={s.chartBox}>
            <SunChart sun={value.data} />
          </div>
          <SourceLine demo={value.demo} text={`${value.data.source}. ${value.data.credit}.`} />
        </>
      )}
    </section>
  );
}

// ---------- (c) a star against the Sun ----------

export function AbundanceBars({ ab }: { ab: Abundances }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const rowH = 30;
  const m = { l: 112, r: 72, t: 8, b: 34 };
  const h = m.t + m.b + ab.elements.length * rowH;
  const lim = Math.max(0.5, ...ab.elements.map((e) => Math.abs(e.x_h_dex) + (e.err_dex ?? 0))) * 1.1;
  const x = log([10 ** -lim, 10 ** lim], [m.l, w - m.r]);
  const vals = [0.25, 0.5, 1, 2, 4].filter((v) => v >= 10 ** -lim && v <= 10 ** lim);
  return (
    <div ref={ref}>
      <svg className={s.svg} width={w} height={h} role="img" aria-label={`${ab.name} compared with the Sun: ${ab.elements.map((e) => `${formatTimesSun(e.x_h_dex)} the Sun's ${elementName(e.symbol)}`).join(", ")}.`}>
        <XAxis x={x} y={h - m.b} values={vals} format={(v) => `${v}×`} grid={[m.t, h - m.b]} title="Compared with the Sun" />
        <line x1={x(1)} x2={x(1)} y1={m.t} y2={h - m.b} stroke="var(--ink-muted)" strokeWidth={1} />
        {ab.elements.map((e, i) => {
          const cy = m.t + i * rowH + rowH / 2;
          const v = 10 ** e.x_h_dex;
          const x0 = Math.min(x(1), x(v));
          const bw = Math.max(1.5, Math.abs(x(v) - x(1)));
          return (
            <g key={e.symbol}>
              <text className={s.chartLabel} x={8} y={cy + 4}>
                <tspan className={s.chartLabelStrong}>{e.symbol}</tspan> {elementName(e.symbol)}
              </text>
              <rect x={x0} y={cy - 7} width={bw} height={14} rx={2} fill={v >= 1 ? "var(--ink)" : "var(--ink-muted)"} opacity={0.85} />
              {e.err_dex != null && (
                <g stroke="var(--ink)" strokeWidth={1.25}>
                  <line x1={x(10 ** (e.x_h_dex - e.err_dex))} x2={x(10 ** (e.x_h_dex + e.err_dex))} y1={cy} y2={cy} />
                  <line x1={x(10 ** (e.x_h_dex - e.err_dex))} x2={x(10 ** (e.x_h_dex - e.err_dex))} y1={cy - 4} y2={cy + 4} />
                  <line x1={x(10 ** (e.x_h_dex + e.err_dex))} x2={x(10 ** (e.x_h_dex + e.err_dex))} y1={cy - 4} y2={cy + 4} />
                </g>
              )}
              <text className={s.chartLabelStrong} x={w - 4} y={cy + 4} textAnchor="end">
                {formatTimesSun(e.x_h_dex)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

export function XpChart({ xp }: { xp: GaiaXp }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = 180;
  const m = { l: 12, r: 12, t: 12, b: 40 };
  const x = linear([xp.wavelength_nm[0], xp.wavelength_nm.at(-1)!], [m.l, w - m.r]);
  const max = Math.max(...xp.flux);
  const y = linear([0, max * 1.08], [h - m.b, m.t]);
  const d = xp.wavelength_nm.map((nm, i) => `${i ? "L" : "M"}${x(nm).toFixed(1)},${y(xp.flux[i]).toFixed(1)}`).join("");
  return (
    <div ref={ref}>
      <svg className={s.svg} width={w} height={h} role="img" aria-label={`Gaia low-resolution spectrum from ${nf0.format(xp.wavelength_nm[0])} to ${nf0.format(xp.wavelength_nm.at(-1)!)} nm.`}>
        <defs>
          <linearGradient id="xp-rb" x1={x(380)} x2={x(750)} y1="0" y2="0" gradientUnits="userSpaceOnUse">
            {RAINBOW.map((nm) => (
              <stop key={nm} offset={(nm - 380) / 370} stopColor={rgbCss(wavelengthRgb(nm))} />
            ))}
          </linearGradient>
          <clipPath id="xp-under">
            <path d={`${d}L${x(xp.wavelength_nm.at(-1)!)},${y(0)}L${x(xp.wavelength_nm[0])},${y(0)}Z`} />
          </clipPath>
        </defs>
        <rect x={x(380)} y={m.t} width={x(750) - x(380)} height={h - m.b - m.t} fill="url(#xp-rb)" opacity={0.7} clipPath="url(#xp-under)" />
        <XAxis x={x} y={h - m.b} values={[400, 600, 800, 1000].filter((v) => v >= x.domain[0] && v <= x.domain[1])} format={(v) => nf0.format(v)} title="Wavelength, nm" />
        <path d={d} fill="none" stroke="var(--ink-secondary)" strokeWidth={1.5} />
      </svg>
    </div>
  );
}

function StarSection({ initialTic }: { initialTic: number | null }) {
  const [tic, setTic] = useState(String(initialTic ?? LAB_STARS[1].tic));
  const ab = useSpectra<Abundances>(abundancesPath(Number(tic)));
  const xp = useSpectra<GaiaXp>(gaiaXpPath(Number(tic)));
  const name = LAB_STARS.find((st) => String(st.tic) === tic)?.name ?? ab.value?.data.name ?? `TIC ${tic}`;
  const fe = ab.value?.data.elements.find((e) => e.symbol === "Fe");
  const options = LAB_STARS.some((st) => String(st.tic) === tic) ? LAB_STARS : [...LAB_STARS, { tic: Number(tic), name }];
  return (
    <section className={s.section} aria-labelledby="star-h">
      <div className={s.sectionHead}>
        <div className={s.titleRow}>
          <h2 id="star-h" className={s.h2}>
            A star&apos;s recipe, against the Sun&apos;s
          </h2>
          {(ab.value?.demo || xp.value?.demo) && <DemoTag />}
        </div>
        <p className={s.body}>
          Measure how deep each element&apos;s lines are and you get how much of it the star holds. Here that is compared with the Sun: a bar to
          the right means more than the Sun, to the left means less.
        </p>
      </div>
      <div>
        <Segmented label="Star" value={tic} onChange={setTic} options={options.map((st) => ({ value: String(st.tic), label: st.name }))} />
      </div>
      <div className={s.bench}>
        <div className={s.chartBox}>
          <div className={s.chartHead}>
            <h3 className={s.h3}>{name}</h3>
            {fe && (
              <span className={s.muted}>
                <span className="mono">{formatTimesSun(fe.x_h_dex)}</span> the Sun&apos;s iron
              </span>
            )}
          </div>
          {ab.loading ? (
            <Skeleton label="Loading abundances" />
          ) : ab.value ? (
            <AbundanceBars ab={ab.value.data} />
          ) : (
            <EmptyState title={`No abundances for ${name} yet`}>They appear here once a survey has measured this star.</EmptyState>
          )}
        </div>
        <div className={s.side}>
          <div className={s.chartBox}>
            <div className={s.chartHead}>
              <h3 className={s.h3}>Its light, from Gaia</h3>
            </div>
            {xp.loading ? <Skeleton label="Loading the Gaia spectrum" /> : xp.value ? <XpChart xp={xp.value.data} /> : <p className={s.help}>No Gaia spectrum for this star yet.</p>}
          </div>
          {ab.value && <SourceLine demo={ab.value.demo} text={ab.value.data.source} />}
          {xp.value && <SourceLine demo={xp.value.demo} text={xp.value.data.credit} />}
          <p className={s.help}>Numbers are ratios to hydrogen, compared with the Sun ([X/H]); bars show the stated uncertainty.</p>
        </div>
      </div>
    </section>
  );
}

// ---------- (d) a planet's air ----------

export function AtmosphereChart({ sp }: { sp: NonNullable<Atmosphere["spectrum"]> }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const h = w < 520 ? 240 : 280;
  const m = { l: 60, r: 12, t: 28, b: 44 };
  const lo = Math.min(...sp.depth_ppm.map((d, i) => d - sp.err_ppm[i]));
  const hi = Math.max(...sp.depth_ppm.map((d, i) => d + sp.err_ppm[i]));
  const pad = (hi - lo) * 0.1;
  const x = linear([Math.min(...sp.wavelength_um), Math.max(...sp.wavelength_um)], [m.l + 8, w - m.r - 8]);
  const y = linear([lo - pad, hi + pad], [h - m.b, m.t]);
  return (
    <div ref={ref}>
      <svg className={s.svg} width={w} height={h} role="img" aria-label={`Transmission spectrum: how much starlight the planet blocks at each wavelength, ${sp.wavelength_um.length} points.`}>
        <XAxis x={x} y={h - m.b} values={ticks(x.domain[0], x.domain[1], 5)} format={(v) => String(v)} title="Wavelength, microns" />
        <YAxis y={y} x={m.l} values={ticks(lo - pad, hi + pad, 4)} format={(v) => nf0.format(v)} grid={[m.l, w - m.r]} title="Light blocked, ppm" />
        {sp.wavelength_um.map((um, i) => (
          <g key={um}>
            <line x1={x(um)} x2={x(um)} y1={y(sp.depth_ppm[i] - sp.err_ppm[i])} y2={y(sp.depth_ppm[i] + sp.err_ppm[i])} stroke="var(--ink-muted)" strokeWidth={1.25} />
            <circle cx={x(um)} cy={y(sp.depth_ppm[i])} r={3.5} fill="var(--ink)" />
          </g>
        ))}
      </svg>
    </div>
  );
}

function PlanetSection() {
  // A star's own lab links here as ?planet=wasp-121-b.
  const asked = useSearchParams().get("planet");
  const [planet, setPlanet] = useState(() => LAB_PLANETS.find((p) => planetSlug(p) === asked) ?? LAB_PLANETS[0]);
  const at = useSpectra<Atmosphere>(atmospherePath(planet));
  const a = at.value?.data;
  return (
    <section className={s.section} aria-labelledby="planet-h" id="planet">
      <div className={s.sectionHead}>
        <div className={s.titleRow}>
          <h2 id="planet-h" className={s.h2}>
            A planet&apos;s air
          </h2>
          {at.value?.demo && <DemoTag />}
        </div>
        <p className={s.body}>
          When a planet crosses its star, a thin ring of starlight shines through its atmosphere. Gases in that air soak up their own colours, so
          the planet looks slightly bigger at those wavelengths. The bumps below are those fingerprints.
        </p>
      </div>
      <div>
        <Segmented label="Planet" value={planet} onChange={setPlanet} options={LAB_PLANETS.map((p) => ({ value: p, label: p }))} />
      </div>
      {at.loading ? (
        <Skeleton label="Loading the atmosphere" />
      ) : !a ? (
        <EmptyState title={`Nothing measured for ${planet} yet`}>Detections appear here once they are published.</EmptyState>
      ) : (
        <div className={s.bench}>
          <div className={s.chartBox}>
            <div className={s.chartHead}>
              <h3 className={s.h3}>{a.planet}: starlight blocked, by colour</h3>
            </div>
            {a.spectrum ? <AtmosphereChart sp={a.spectrum} /> : <p className={s.help} style={{ padding: "var(--s-4) var(--s-1)" }}>No spectrum in this file, only the detections listed alongside.</p>}
          </div>
          <div className={s.side}>
            <div className={s.block}>
              <span className="label">Found in its air</span>
              <ul className={s.species}>
                {a.detections.map((d) => (
                  <li key={d.species} className={s.speciesItem} title={d.reference}>
                    <b>{formula(d.species)}</b>
                    <span>{speciesName(d.species)}</span>
                  </li>
                ))}
              </ul>
              <SourceLine demo={at.value!.demo} text={a.source} />
            </div>
          </div>
        </div>
      )}
    </section>
  );
}

export function Fingerprints({ initialTic }: { initialTic: number | null }) {
  return (
    <div className={s.sectionGap}>
      <Note icon={<Info size={14} aria-hidden />}>
        Everything on this page is measured light turned into barcodes and numbers. None of it is a photo: the colours are drawn from the
        wavelengths. <Tag>Demo data</Tag> marks stand-in files until the real spectra are in.
      </Note>
      <BarcodeLab />
      <SunSection />
      <StarSection initialTic={initialTic} />
      <PlanetSection />
    </div>
  );
}

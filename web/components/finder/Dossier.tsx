"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiError, getCandidate, type Candidate, type CandidateReport, type Vetting } from "@/lib/api";
import { btjdToMs, fmtDate, fmtDepth, fmtPeriod, fmtRadius, fmtTemp, fmtTmag, observedLine, sectorWord, starKind } from "@/components/monitor/format";
import { checkLabel, fmtSize, KNOWN_LISTS, listMatch, sizeClass, transitTimes } from "./finder";
import { buildTape, tapeX } from "@/components/monitor/trace";
import { InkPlot, type Series } from "./InkPlot";
import { PixelCheck } from "./PixelCheck";
import { VoteBox } from "./VoteBox";
import s from "./finder.module.css";

const r = (x: number, n = 2) => Number(x.toFixed(n));

function DipPlots({ c }: { c: Candidate }) {
  const folded = useMemo(() => {
    const half = Math.max(3 * c.duration_h, 3);
    let zx: number[] = [];
    let zy: number[] = [];
    if (c.folded_zoom?.hours_from_mid.length) {
      zx = c.folded_zoom.hours_from_mid;
      zy = c.folded_zoom.flux;
    } else {
      c.folded.phase.forEach((p, i) => {
        const h = p * c.period_d * 24;
        if (Math.abs(h) <= half) {
          zx.push(h);
          zy.push(c.folded.flux[i]);
        }
      });
    }
    const xMax = Math.max(half, ...zx.map(Math.abs));
    const lo = Math.min(...zy);
    const hi = Math.max(...zy);
    const pad = (hi - lo) * 0.18 || 1e-3;
    const ticks = [-1, -0.5, 0, 0.5, 1].map((k) => {
      const h = k * xMax;
      return { at: h, text: `${h > 0 ? "+" : h < 0 ? "\u2212" : ""}${Math.abs(r(h, 1))} h` };
    });
    const series: Series[] = [
      { x: zx, y: zy, style: "line", colour: "pen" },
      { x: zx, y: zy, style: "dots", colour: "ink" },
    ];
    return { series, x: [-xMax, xMax] as [number, number], y: [lo - pad, hi + pad] as [number, number], ticks };
  }, [c]);

  const unfolded = useMemo(() => {
    // the whole curve with the months between sectors closed up, as on the monitor
    const tape = buildTape({ lightcurve: { t: c.unfolded.time_btjd, f: c.unfolded.flux }, detections: [], sectors: c.sectors });
    const f = c.unfolded.flux;
    const sorted = [...f].sort((p, q) => p - q);
    const lo = sorted[Math.floor(sorted.length * 0.001)];
    const hi = sorted[Math.floor(sorted.length * 0.999)];
    const pad = (hi - lo) * 0.12 || 1e-3;
    const t = c.unfolded.time_btjd;
    const marks = transitTimes(c.t0_btjd, c.period_d, t[0], t[t.length - 1])
      .map((tm) => tapeX(tape, tm))
      .filter((x): x is number => x != null);
    const ticks = tape.segments
      .filter((sg, k) => k === 0 || sg.t0 - tape.segments[k - 1].t1 > 10)
      .map((sg) => ({ at: sg.x0, text: `${fmtDate(btjdToMs(sg.t0)).replace(/^\d+ /, "")}${sg.sector != null ? `, S${sg.sector}` : ""}` }));
    return {
      series: [{ x: Array.from(tape.x), y: f, style: "dots", colour: "ink" }] as Series[],
      x: [0, tape.length] as [number, number],
      y: [lo - pad, hi + pad] as [number, number],
      ticks,
      marks,
    };
  }, [c]);

  return (
    <div className={s.plots}>
      <figure className={s.fig}>
        <InkPlot
          series={folded.series}
          xRange={folded.x}
          yRange={folded.y}
          xTicks={folded.ticks}
          xLabel="hours from the middle of the dip"
          yLabel="brightness"
          label={`All ${c.n_transits} dips stacked on the ${fmtPeriod(c.period_d)} period: the light drops by ${fmtDepth(c.depth_ppm)} for ${c.duration_h.toFixed(1)} hours.`}
        />
        <figcaption className={s.cap}>
          Every dip stacked on one period and averaged. A planet makes a flat-bottomed dip; two stars grazing each other make a V.
        </figcaption>
      </figure>
      <figure className={s.fig}>
        <InkPlot
          series={unfolded.series}
          xRange={unfolded.x}
          yRange={unfolded.y}
          xTicks={unfolded.ticks}
          marks={unfolded.marks}
          xLabel="months between sectors closed up"
          yLabel="brightness, 30 min bins"
          height={200}
          label={`The whole light curve with each of the ${unfolded.marks.length} expected dips marked.`}
        />
        <figcaption className={s.cap}>The whole light curve. Red ticks mark where each dip should fall.</figcaption>
      </figure>
    </div>
  );
}

function Checks({ c }: { c: Candidate }) {
  return (
    <ol className={s.checks}>
      {c.checks.map((ch) => {
        const word = ch.passed === true ? "passed" : ch.passed === false ? "failed" : "note";
        return (
          <li key={ch.name} className={s.check} data-passed={String(ch.passed)}>
            <span className={`label ${s.checkWord}`}>{word}</span>
            <span className={s.checkName}>{checkLabel(ch.name)}</span>
            <span className={s.checkReason}>{ch.reason}</span>
          </li>
        );
      })}
    </ol>
  );
}

function VettingBlock({ v }: { v: Vetting }) {
  const mimic = v.gaia.neighbours.filter((n) => n.can_mimic);
  const rows: { name: string; what: string; result: string; ran: boolean }[] = [
    {
      name: "LEO",
      what: "Automated vetting of the light curve's shape",
      ran: v.leo.ran,
      result: v.leo.ran ? (v.leo.passed ? "passed" : `flagged: ${v.leo.flags.join(", ") || "see flags"}`) : "not run yet",
    },
    {
      name: "TRICERATOPS",
      what: "Chance the dip comes from something other than a planet on this star",
      ran: v.triceratops.ran,
      result: v.triceratops.ran && v.triceratops.fpp != null ? `false-positive chance ${Math.round(v.triceratops.fpp * 100)}%${v.triceratops.nfpp != null ? `, from a nearby star ${Math.round(v.triceratops.nfpp * 100)}%` : ""}` : "not run yet",
    },
    {
      name: "Gaia DR3",
      what: "Is the star single, and could a neighbour fake the dip?",
      ran: true,
      result: `${v.gaia.ruwe != null ? `RUWE ${v.gaia.ruwe.toFixed(2)}${v.gaia.binary_hint ? ", hints at a binary" : ", a single star"}` : "no RUWE"}; ${mimic.length === 0 ? "no neighbour within 42″ is bright enough to fake it" : `${mimic.length} neighbour${mimic.length > 1 ? "s" : ""} within 42″ could be`}`,
    },
    {
      name: "Variability",
      what: "Is the star a known variable?",
      ran: true,
      result: v.variability.vsx_match ? `in VSX as ${v.variability.vsx_match.name} (${v.variability.vsx_match.type})` : v.variability.gaia_variable ? "Gaia flags it as variable" : "not in VSX, not flagged by Gaia",
    },
  ];
  return (
    <>
      <p className={s.verdictLine}>
        <span className={s.verdict} data-verdict={v.summary.verdict}>
          {v.summary.verdict}
        </span>
      </p>
      <ul className={s.reasonsList}>
        {v.summary.reasons.map((x) => (
          <li key={x}>{x}</li>
        ))}
      </ul>
      <dl className={s.vetRows}>
        {rows.map((x) => (
          <div key={x.name} className={s.vetRow} data-ran={x.ran}>
            <dt>
              <span className={s.vetName}>{x.name}</span>
              <span className={s.cap}>{x.what}</span>
            </dt>
            <dd className={x.ran ? undefined : "italic quiet"}>{x.result}</dd>
          </div>
        ))}
      </dl>
    </>
  );
}

function Margin({ c }: { c: Candidate }) {
  const t = c.unfolded.time_btjd;
  const from = t.length ? new Date(btjdToMs(t[0])).toISOString() : null;
  const to = t.length ? new Date(btjdToMs(t[t.length - 1])).toISOString() : null;
  const st = c.star;
  return (
    <aside className={s.margin} aria-label="The star and the data">
      <dl className={s.marginList}>
        <div>
          <dt className="label">Star</dt>
          <dd>
            TIC {c.tic}
            {st && <span className={s.sub}>{starKind(st.teff, st.rad)}</span>}
          </dd>
        </div>
        {st && (
          <div>
            <dt className="label">Catalogue</dt>
            <dd className="num">
              {[fmtTmag(st.tmag), fmtTemp(st.teff), fmtRadius(st.rad)].filter(Boolean).join(" · ")}
              <span className={s.sub}>
                RA {st.ra.toFixed(4)}°, Dec {st.dec.toFixed(4)}°
              </span>
            </dd>
          </div>
        )}
        <div>
          <dt className="label">Data</dt>
          <dd>
            {observedLine(from, to, c.sectors)}
            <span className={s.sub}>{sectorWord(c.sectors)}</span>
          </dd>
        </div>
        <div>
          <dt className="label">Known lists</dt>
          <dd className={s.lists}>
            {KNOWN_LISTS.map((l) => {
              const m = listMatch(c.known_lists[l.key]);
              return (
                <span key={l.key} data-matched={m.matched}>
                  {l.label}: {m.matched ? (m.id ?? "listed") : "not listed"}
                </span>
              );
            })}
          </dd>
        </div>
        <div>
          <dt className="label">Searched</dt>
          <dd>{fmtDate(c.created_at)}</dd>
        </div>
        <div>
          <dt className="label">Elsewhere</dt>
          <dd>
            <a href={`https://exofop.ipac.caltech.edu/tess/target.php?id=${c.tic}`} rel="noreferrer" target="_blank">
              ExoFOP page for TIC {c.tic}
            </a>
          </dd>
        </div>
      </dl>
    </aside>
  );
}

export function Dossier({ id }: { id: string }) {
  const [rep, setRep] = useState<CandidateReport | null>(null);
  const [error, setError] = useState<{ status: number | null; message: string } | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    getCandidate(id, ac.signal)
      .then(setRep)
      .catch((e: unknown) => !ac.signal.aborted && setError({ status: e instanceof ApiError ? e.status : null, message: e instanceof Error ? e.message : String(e) }));
    return () => ac.abort();
  }, [id]);

  if (error)
    return (
      <div className={`wrap ${s.page}`}>
        <p className={s.crumb}>
          <Link href="/candidates">Candidates</Link>
        </p>
        <h1>{error.status === 404 ? "No candidate by that name" : "The dossier could not be loaded"}</h1>
        <p className="italic quiet">{error.status === 404 ? "It may have been withdrawn after review." : error.message}</p>
      </div>
    );
  if (!rep)
    return (
      <div className={`wrap ${s.page}`}>
        <div className={s.skeleton} role="status" aria-label="Loading the dossier" />
      </div>
    );

  const c = rep.candidate;
  return (
    <article className={`wrap ${s.page}`}>
      <p className={s.crumb}>
        <Link href="/candidates">Candidates</Link>
      </p>
      <header className={s.dossierHead}>
        <p className="label">Planet candidate, not a confirmed planet</p>
        <h1 className={s.dossierTitle}>TIC {c.tic}</h1>
        <p className={s.dossierSub}>
          A dip every {fmtPeriod(c.period_d)}, {fmtDepth(c.depth_ppm)} deep, lasting {c.duration_h.toFixed(1)} hours. If it is a planet, it is {fmtSize(c.radius_rjup)} ({sizeClass(c.radius_rjup)}).
        </p>
        {c.stand_in && (
          <p className={`sheet ${s.standIn}`}>
            <span className="label">Stand-in</span> {c.stand_in.note}
          </p>
        )}
      </header>

      <div className={s.dossierGrid}>
        <div className={s.main}>
          <section aria-labelledby="dip">
            <h2 id="dip">The dip</h2>
            <dl className={s.numbers}>
              {[
                ["Period", fmtPeriod(c.period_d)],
                ["Depth", fmtDepth(c.depth_ppm)],
                ["Length", `${c.duration_h.toFixed(1)} h`],
                ["Dips seen", String(c.n_transits)],
                ["Strength", `${c.snr.toFixed(1)} × noise`],
              ].map(([k, v]) => (
                <div key={k}>
                  <dt className="label">{k}</dt>
                  <dd>{v}</dd>
                </div>
              ))}
            </dl>
            <DipPlots c={c} />
          </section>

          <section aria-labelledby="checks">
            <h2 id="checks">The checks</h2>
            <p className="quiet">Each test the search runs before it keeps a signal, in its own words.</p>
            <Checks c={c} />
          </section>

          <section aria-labelledby="pixels">
            <h2 id="pixels">The pixel check</h2>
            <p className="quiet">Which star in the TESS pixels the light really went missing from.</p>
            {rep.pixels ? <PixelCheck vet={rep.pixels} /> : <p className="italic quiet">Not run yet for this signal.</p>}
          </section>

          <section aria-labelledby="vetting">
            <h2 id="vetting">Vetting</h2>
            {c.vetting ? <VettingBlock v={c.vetting} /> : <p className="italic quiet">Not vetted yet.</p>}
          </section>

          <section aria-labelledby="votes">
            <h2 id="votes">Votes</h2>
            <VoteBox id={c.id} initial={rep.votes} demo={rep.demo} />
          </section>
        </div>
        <Margin c={c} />
      </div>
    </article>
  );
}

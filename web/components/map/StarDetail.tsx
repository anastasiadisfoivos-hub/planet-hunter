"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ArrowSquareOut, CheckCircle, Circle, CircleNotch, Flask, X } from "@phosphor-icons/react";
import { ChemicalFingerprint } from "@/components/lab/ChemicalFingerprint";
import { Button, DataGrid, DemoTag, Tag } from "@/components/ui";
import { analyze, API_MOCK, getJob, type AnalyzeJob, type AnalyzeTarget } from "@/lib/api";
import type { MapData } from "@/lib/data";
import { formatPercent } from "@/lib/format";
import { bvToTeff, starColor } from "@/lib/starColor";
import { formatDec, formatRa } from "@/lib/sky";
import type { StarRef } from "@/state/store";
import s from "./map.module.css";

const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });

type StarFacts = {
  kind: "Planet host" | "Star";
  name: string;
  ra: number;
  dec: number;
  teff: number;
  teffNote: string;
  radius: number;
  radiusNote: string;
  dist: number;
  vmag: number | null;
  planets: string[];
  target: AnalyzeTarget;
};

/** Everything the panel says about a star, from the catalogues (and which catalogue). */
export function starFacts(data: MapData, ref: StarRef): StarFacts {
  if (ref.kind === "host") {
    const h = data.hosts;
    const i = ref.i;
    return {
      kind: "Planet host",
      name: h.name[i],
      ra: h.ra[i],
      dec: h.dec[i],
      teff: h.teff[i],
      teffNote: "TESS Input Catalog, via the NASA Exoplanet Archive",
      radius: h.rad?.[i] ?? 0,
      radiusNote: "NASA Exoplanet Archive",
      dist: h.dist[i],
      vmag: h.vmag?.[i] != null && h.vmag[i] < 99 ? h.vmag[i] : null,
      planets: h.planets?.[i] ?? [],
      target: { name: h.name[i], tic_id: h.tic[i], ra_deg: h.ra[i], dec_deg: h.dec[i] },
    };
  }
  const st = data.sky.stars;
  const b = data.bright;
  const i = ref.i;
  const teff = Number.isFinite(st.bv[i]) ? Math.round(bvToTeff(st.bv[i]) / 10) * 10 : 0;
  // Not catalogued: estimated from luminosity and temperature, R = sqrt(L) (5772 K / T)^2.
  const radius = b.lum[i] > 0 && teff > 0 ? Math.sqrt(b.lum[i]) * (5772 / teff) ** 2 : 0;
  const name = b.name[i] || `Star at ${formatRa(st.ra[i])} ${formatDec(st.dec[i])}`;
  return {
    kind: "Star",
    name,
    ra: st.ra[i],
    dec: st.dec[i],
    teff,
    teffNote: "Estimated from its colour (B−V)",
    radius,
    radiusNote: "Estimated from its brightness and temperature",
    dist: b.dist[i],
    vmag: st.mag[i],
    // A bright star that is also a known host keeps its planets, even with the hosts layer off.
    planets: b.host[i] >= 0 ? (data.hosts.planets?.[b.host[i]] ?? []) : [],
    target: { name, hip: b.hip[i] || undefined, ra_deg: st.ra[i], dec_deg: st.dec[i] },
  };
}

function Analysis({ target }: { target: AnalyzeTarget }) {
  const [job, setJob] = useState<AnalyzeJob | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
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
          if (j.status !== "done" && j.status !== "failed") timer = window.setTimeout(poll, 400);
        })
        .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    poll();
    return () => {
      live = false;
      clearTimeout(timer);
    };
  }, [jobId]);

  const start = () => {
    setError(null);
    setJob(null);
    analyze(target)
      .then((r) => setJobId(r.job_id))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  };

  if (!jobId) {
    return (
      <div className={s.analyze}>
        <Button variant="primary" onClick={start}>
          Analyze this star
        </Button>
        <p className={s.help}>Searches this star&apos;s TESS light curve for repeating dips (possible planets) and flares.</p>
        {error && (
          <p className={s.help} role="alert">
            {error}
          </p>
        )}
      </div>
    );
  }

  const r = job?.result;
  return (
    <section className={s.analyze} aria-label="Analysis" aria-live="polite">
      <div className={s.rowBetween}>
        <h3 className={s.h4}>Analysis</h3>
        {API_MOCK && <DemoTag />}
      </div>
      <ol className={s.steps}>
        {(job?.steps ?? []).map((st) => (
          <li key={st.key} data-state={st.state}>
            {st.state === "done" ? <CheckCircle size={16} weight="fill" aria-hidden /> : st.state === "running" ? <CircleNotch size={16} className={s.spin} aria-hidden /> : <Circle size={16} aria-hidden />}
            <span>{st.label}</span>
            <span className="mono">{st.seconds != null ? `${st.seconds.toFixed(1)} s` : ""}</span>
          </li>
        ))}
      </ol>
      {error && (
        <p className={s.help} role="alert">
          {error}
        </p>
      )}
      {r && (
        <div className={s.result}>
          {job?.demo && (
            <p className={s.help}>
              Demo: this is the stored analysis of WASP-18, shown for any star until the analysis service is connected. It is not a result for{" "}
              {target.name}.
            </p>
          )}
          <p className={s.help}>
            TESS sectors {r.data.map((d) => d.sector).join(" and ")}, {r.data[0]?.exptime ?? 120} s cadence ({r.data[0]?.author}). {r.flares_found} flares found.
          </p>
          {r.discoveries.map((d) => (
            <article key={d.id} className={s.resultItem}>
              <div className={s.rowBetween}>
                <p className={s.h4}>
                  {d.type === "planet_candidate" ? "Planet candidate" : d.type.replace(/_/g, " ")}
                  {d.name_if_known ? `: ${d.name_if_known}` : ""}
                </p>
                <Tag>{formatPercent(d.confidence)}</Tag>
              </div>
              <p className={s.summary}>{d.explanation}</p>
              <ul className={s.linkList}>
                {d.links.map((l) => (
                  <li key={l.url}>
                    <a href={l.url} target="_blank" rel="noreferrer">
                      {l.label}
                      <ArrowSquareOut size={12} aria-hidden />
                    </a>
                  </li>
                ))}
              </ul>
            </article>
          ))}
          {job?.plotBase &&
            r.plots.map((p) => (
              <figure key={p} className={s.plot}>
                {/* eslint-disable-next-line @next/next/no-img-element -- pipeline plot, stored with the result */}
                <img src={job.plotBase + p} alt="The light curve folded on the signal's period, showing the repeating dip." loading="lazy" />
                <figcaption className={s.caption}>Light curve folded on the signal&apos;s period (TESS, via the analysis pipeline).</figcaption>
              </figure>
            ))}
          <Button size="sm" onClick={start}>
            Run again
          </Button>
        </div>
      )}
    </section>
  );
}

export function StarDetail({ data, star, onBack }: { data: MapData; star: StarRef; onBack: () => void }) {
  const f = starFacts(data, star);
  const [r, g, b] = starColor(f.teff).map((v) => Math.round(v * 255));
  const hostI = star.kind === "host" ? star.i : data.bright.host[star.i];
  const fpTic = hostI >= 0 ? data.hosts.tic[hostI] : 0;
  return (
    <article className={s.detail} aria-label={f.name}>
      <div className={s.detailHead}>
        <Button variant="quiet" size="sm" icon={<X size={16} />} onClick={onBack}>
          Close
        </Button>
      </div>
      <div className={s.stackTight}>
        <p className={`mono ${s.rowType}`}>
          <span className={s.starSwatch} style={{ background: `rgb(${r} ${g} ${b})` }} aria-hidden />
          {f.kind}
        </p>
        <h2 className={s.detailTitle}>{f.name}</h2>
      </div>
      <DataGrid
        items={[
          { label: "Temperature", value: f.teff > 0 ? `${nf.format(f.teff)} K` : "Not listed", mono: true, hint: f.teff > 0 ? f.teffNote : undefined },
          {
            label: "Radius",
            value: f.radius > 0 ? `${star.kind === "bright" ? "≈ " : ""}${f.radius < 10 ? f.radius.toFixed(2) : nf.format(f.radius)} R☉` : "Not listed",
            mono: true,
            hint: f.radius > 0 ? f.radiusNote : undefined,
          },
          {
            label: "Distance",
            value: f.dist > 0 ? `${f.dist < 10 ? f.dist.toFixed(2) : nf.format(f.dist)} pc` : "Not listed",
            mono: true,
            hint: f.dist > 0 ? `About ${nf.format(f.dist * 3.2616)} light-years` : undefined,
          },
          { label: "Brightness", value: f.vmag != null ? `${f.vmag.toFixed(2)} mag` : "Not listed", mono: true },
          {
            label: "Known planets",
            value: f.planets.length ? f.planets.join(", ") : "None known",
            wide: true,
          },
        ]}
      />
      {star.kind === "host" && <p className={s.help}>Close-up surface is an illustration; colour, size and position are from real data.</p>}
      {fpTic > 0 && (
        <div>
          <Link className={s.linkButton} href={`/lab/star/${fpTic}`}>
            <Flask size={14} aria-hidden />
            Open in Lab
          </Link>
        </div>
      )}
      {fpTic > 0 && <ChemicalFingerprint tic={fpTic} />}
      <Analysis key={`${star.kind}:${star.i}`} target={f.target} />
    </article>
  );
}

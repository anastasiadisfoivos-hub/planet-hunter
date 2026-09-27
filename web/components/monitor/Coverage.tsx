"use client";

import { useEffect, useMemo, useState } from "react";
import type { CoverageStar, StarOutcome } from "@/lib/api";
import { OUTCOME_WORD, thousands } from "./format";
import { eclipticLine, galacticLine, skyPath, skyXY } from "./sky";
import { starHex } from "./starColour";
import { TempKey } from "./TempKey";
import s from "./log.module.css";

const W = 1000;
const H = W / 2;
const ORDER: StarOutcome[] = ["candidate", "known", "rejected", "none"];

type Sectors = { sectors: { sector: number; ccds: { camera: number; ccd: number; edge: [number, number][] }[] }[] };

/** The latest TESS footprints, computed with tess-point: static reference data, the same in mock and live. */
function useSectors(): Sectors | null {
  const [s, set] = useState<Sectors | null>(null);
  useEffect(() => {
    const ac = new AbortController();
    fetch("/data/monitor/sectors.json", { signal: ac.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then(set)
      .catch(() => {});
    return () => ac.abort();
  }, []);
  return s;
}

/** The outcome's ring: candidate a thick pen ring, known a blue ring, rejected thin ink, nothing found dashed. */
function Dot({ o, x, y, teff, title }: { o: StarOutcome; x: number; y: number; teff: number | null; title?: string }) {
  return (
    <circle cx={x} cy={y} r={o === "candidate" ? 6 : 4.5} className={s.dot} data-outcome={o} style={{ fill: starHex(teff) ?? "var(--paper)" }}>
      {title && <title>{title}</title>}
    </circle>
  );
}

/** Where in the sky the search has looked: one dot per star, coloured by the star's temperature, on a Mollweide map. */
export function Coverage({ stars, teffOf }: { stars: CoverageStar[]; teffOf: Map<number, number | null> }) {
  const sectors = useSectors();
  const counts = Object.fromEntries(ORDER.map((o) => [o, stars.filter((x) => x.outcome === o).length])) as Record<StarOutcome, number>;
  const sorted = useMemo(() => [...stars].sort((a, b) => ORDER.indexOf(b.outcome) - ORDER.indexOf(a.outcome)), [stars]);
  const frame = useMemo(() => {
    const outline: [number, number][] = [...Array.from({ length: 91 }, (_, i) => [179.999, 90 - i * 2] as [number, number]), ...Array.from({ length: 91 }, (_, i) => [180.001, -90 + i * 2] as [number, number])];
    return {
      outline: skyPath(outline, W, true),
      meridians: [30, 60, 90, 120, 150, 210, 240, 270, 300, 330, 0].map((ra) => skyPath(Array.from({ length: 61 }, (_, i) => [ra, -90 + i * 3]), W)),
      parallels: [-60, -30, 0, 30, 60].map((dec) => ({ dec, d: skyPath(Array.from({ length: 121 }, (_, i) => [180.001 + i * 3 - 0.002 * (i === 120 ? 1 : 0), dec]), W) })),
      plane: skyPath(galacticLine(0), W),
      edges: [skyPath(galacticLine(10), W), skyPath(galacticLine(-10), W)],
      ecliptic: skyPath(eclipticLine(), W),
    };
  }, []);
  const latest = sectors?.sectors.map((x) => x.sector) ?? [];
  const label = (ra: number, dec: number) => skyXY(ra, dec, W);
  return (
    <figure className={s.coverage}>
      <svg viewBox={`-6 -6 ${W + 12} ${H + 12}`} className={s.sky} role="img" aria-label={`All-sky map of the ${stars.length} stars searched, coloured by temperature, with the Milky Way, the ecliptic and TESS's latest sectors.`}>
        <path d={frame.outline} className={s.skyBg} />
        <g className={s.graticule}>
          {frame.meridians.map((d, i) => (
            <path key={i} d={d} />
          ))}
          {frame.parallels.map((p) => (
            <path key={p.dec} d={p.d} />
          ))}
        </g>
        <path d={frame.plane} className={s.milkyWay} />
        {frame.edges.map((d, i) => (
          <path key={i} d={d} className={s.milkyEdge} />
        ))}
        <path d={frame.ecliptic} className={s.ecliptic} />
        {sectors?.sectors.map((sec) => (
          <g key={sec.sector} className={s.sector}>
            {sec.ccds.map((c) => (
              <path key={`${c.camera}-${c.ccd}`} d={skyPath(c.edge, W, true)} />
            ))}
          </g>
        ))}
        {sorted.map((x) => (
          <Dot key={x.tic} o={x.outcome} x={skyXY(x.ra, x.dec, W)[0]} y={skyXY(x.ra, x.dec, W)[1]} teff={teffOf.get(x.tic) ?? null} title={`TIC ${x.tic}: ${OUTCOME_WORD[x.outcome]}`} />
        ))}
        <text x={label(266, -29)[0] + 8} y={label(266, -29)[1] + 22} className={s.skyNote}>
          Milky Way
        </text>
        <text x={label(40, 16)[0]} y={label(40, 16)[1] - 6} className={s.skyNote}>
          ecliptic
        </text>
        {[0, 6, 18].map((h) => (
          <text key={h} x={label(h * 15, 0)[0]} y={label(h * 15, 0)[1] + 14} className={s.skyLabel} textAnchor="middle">
            {h}h
          </text>
        ))}
        {[60, 30, -30, -60].map((d) => (
          <text key={d} x={label(179.99, d)[0] - 8} y={label(179.99, d)[1] + 4} className={s.skyLabel} textAnchor="end">
            {d > 0 ? `+${d}` : `−${-d}`}°
          </text>
        ))}
      </svg>
      <figcaption className={s.legend}>
        <div className={s.legendGroup}>
          {ORDER.map((o) => (
            <span key={o} className={s.legendItem}>
              <svg viewBox="-7 -7 14 14" aria-hidden>
                <Dot o={o} x={0} y={0} teff={5700} />
              </svg>
              <span className="num">{thousands(counts[o])}</span> <span>{OUTCOME_WORD[o]}</span>
            </span>
          ))}
        </div>
        <TempKey />
        <p className={s.legendNote}>
          Mollweide projection, RA 0h at the centre and increasing to the left. Faint band: the Milky Way. Dashed: the ecliptic.
          {latest.length > 0 && ` Outlines: TESS's CCDs in sectors ${latest.join(", ")}.`}
        </p>
      </figcaption>
    </figure>
  );
}

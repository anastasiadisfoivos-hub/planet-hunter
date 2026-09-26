import type { CoverageStar, StarOutcome } from "@/lib/api";
import { OUTCOME_WORD, thousands } from "./format";
import s from "./log.module.css";

const W = 720;
const H = 360;
/** Equirectangular sky, RA increasing to the left as when looking up, RA 0h at the right-hand edge. */
const px = (ra: number) => W - (ra / 360) * W;
const py = (dec: number) => ((90 - dec) / 180) * H;

const ORDER: StarOutcome[] = ["candidate", "known", "rejected", "none"];

function Dot({ o, x, y }: { o: StarOutcome; x: number; y: number }) {
  return <circle cx={x} cy={y} r={o === "candidate" ? 4 : 3} className={s.dot} data-outcome={o} />;
}

/** Where in the sky the search has looked: one dot per star searched. */
export function Coverage({ stars }: { stars: CoverageStar[] }) {
  const counts = Object.fromEntries(ORDER.map((o) => [o, stars.filter((x) => x.outcome === o).length])) as Record<StarOutcome, number>;
  const sorted = [...stars].sort((a, b) => ORDER.indexOf(b.outcome) - ORDER.indexOf(a.outcome));
  return (
    <figure className={s.coverage}>
      <svg viewBox={`-28 -8 ${W + 36} ${H + 30}`} className={s.sky} role="img" aria-label={`Sky map of the ${stars.length} stars searched, by right ascension and declination.`}>
        <rect x={0} y={0} width={W} height={H} className={s.skyBg} />
        {[30, 60, 90, 120, 150].map((d) => (
          <g key={d}>
            <line x1={0} x2={W} y1={py(90 - d)} y2={py(90 - d)} className={d === 90 ? s.skyMajor : s.skyMinor} />
          </g>
        ))}
        {Array.from({ length: 11 }, (_, k) => (k + 1) * 30).map((ra) => (
          <line key={ra} x1={px(ra)} x2={px(ra)} y1={0} y2={H} className={ra === 180 ? s.skyMajor : s.skyMinor} />
        ))}
        {[0, 6, 12, 18, 24].map((h) => (
          <text key={h} x={px(h * 15)} y={H + 18} className={s.skyLabel} textAnchor={h === 0 ? "end" : h === 24 ? "start" : "middle"}>
            {h}h
          </text>
        ))}
        {[60, 30, 0, -30, -60].map((d) => (
          <text key={d} x={-6} y={py(d) + 3.5} className={s.skyLabel} textAnchor="end">
            {d > 0 ? `+${d}` : d === 0 ? "0" : `−${-d}`}°
          </text>
        ))}
        {sorted.map((x) => (
          <Dot key={x.tic} o={x.outcome} x={px(x.ra)} y={py(x.dec)} />
        ))}
      </svg>
      <figcaption className={s.legend}>
        {ORDER.map((o) => (
          <span key={o} className={s.legendItem}>
            <svg viewBox="-5 -5 10 10" aria-hidden>
              <Dot o={o} x={0} y={0} />
            </svg>
            <span className="num">{thousands(counts[o])}</span> <span>{OUTCOME_WORD[o]}</span>
          </span>
        ))}
        <span className="label">Right ascension across, declination up</span>
      </figcaption>
    </figure>
  );
}

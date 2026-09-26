import type { MonitorStar } from "@/lib/api";
import { fmtRadius, fmtTemp, fmtTmag, observedLine, sectorWord, starKind } from "./format";
import s from "./monitor.module.css";

/** The star being drawn: its name, what kind of star it is, and when TESS observed it. */
export function StarHeader({ star }: { star: MonitorStar }) {
  const facts = [fmtTmag(star.tmag), fmtTemp(star.teff), fmtRadius(star.radius_rsun)].filter(Boolean);
  return (
    <div className={s.starHead} key={star.tic}>
      <h1 className={s.starName}>
        <span className={s.tic}>TIC</span> {star.tic}
      </h1>
      <p className={s.starKind}>
        {starKind(star.teff, star.radius_rsun)}
        <span className={s.facts}>
          {facts.map((f) => (
            <span key={f} className="num">
              {f}
            </span>
          ))}
        </span>
      </p>
      <p className={s.observed}>
        {observedLine(star.observed_from, star.observed_to, star.sectors)}
        <span className="label"> · {sectorWord(star.sectors)}</span>
      </p>
    </div>
  );
}

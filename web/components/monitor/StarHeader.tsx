import type { MonitorStar } from "@/lib/api";
import { fmtRadius, fmtTemp, fmtTmag, observedLine, sectorWord, starKind } from "./format";
import { StarGlyph } from "./Glyphs";
import { starHex } from "./starColour";
import s from "./monitor.module.css";

/** The star on the paper: its name with its colour, what kind of star it is, and when TESS observed it. */
export function StarHeader({ star }: { star: MonitorStar }) {
  const facts = [fmtTmag(star.tmag), fmtTemp(star.teff), fmtRadius(star.radius_rsun)].filter(Boolean);
  return (
    <div className={s.starHead} key={star.tic} style={{ ["--star" as string]: starHex(star.teff) ?? "var(--ink-3)" }}>
      <div className={s.nameRow}>
        <StarGlyph teff={star.teff} radius={star.radius_rsun} size={64} />
        <h1 className={s.starName}>
          <span className={s.tic}>TIC</span> {star.tic}
        </h1>
      </div>
      <span className={s.starRule} aria-hidden />
      <p className={s.starKind}>
        <span className={s.kindWord}>{starKind(star.teff, star.radius_rsun)}</span>
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

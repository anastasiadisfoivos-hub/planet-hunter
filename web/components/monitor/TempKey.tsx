import { scaleGradient, SCALE_TEMPS } from "./starColour";
import s from "./glyphs.module.css";

/** The key for star colours: the blackbody scale from cool to hot, with its temperatures. */
export function TempKey({ compact = false }: { compact?: boolean }) {
  const ends = [SCALE_TEMPS[0], 5800, SCALE_TEMPS[SCALE_TEMPS.length - 1]];
  return (
    <div className={s.key} data-compact={compact || undefined}>
      <span className="label">Star colour: its temperature</span>
      <span className={s.keyBar} style={{ background: scaleGradient() }} aria-hidden />
      <span className={s.keyTicks} aria-hidden>
        {ends.map((t) => (
          <span key={t} className="num" style={{ left: `${((SCALE_TEMPS.indexOf(t) >= 0 ? SCALE_TEMPS.indexOf(t) : 3.3) / (SCALE_TEMPS.length - 1)) * 100}%` }}>
            {t === 5800 ? "Sun" : `${t.toLocaleString("en-GB").replace(",", " ")} K`}
          </span>
        ))}
      </span>
      <span className="sr-only">Blackbody colour from about 2 500 K, orange-red, through the Sun at 5 800 K, near white, to 10 000 K, blue-white.</span>
    </div>
  );
}

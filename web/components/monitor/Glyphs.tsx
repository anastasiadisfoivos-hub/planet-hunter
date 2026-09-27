// Hand-drawn glyphs in the chart recorder's line (DESIGN.md: Glyphs). One stroke weight everywhere (1.25 px at
// the drawn size), round caps, ink colour; the only fill is a star's own temperature colour. No clip-art.

import { starClass, type StarClass } from "./format";
import { starHex } from "./starColour";
import s from "./glyphs.module.css";

const STROKE = 1.25;

/** Disc radius by type, out of a 32 px box: red dwarfs small, F and hotter larger, giants fill the box. */
const R: Record<string, number> = { M: 5, K: 6.5, G: 8, F: 9, A: 10, B: 10.5 };

/**
 * A star by type: a disc sized by its class and filled with its blackbody colour, a short limb arc drawn inside
 * like a pen's second pass, and for evolved stars a dotted envelope. The title says what it shows.
 */
export function StarGlyph({ teff, radius, size = 28, title }: { teff: number | null; radius: number | null; size?: number; title?: string }) {
  const c: StarClass = starClass(teff, radius);
  const fill = starHex(teff) ?? "transparent";
  const r = c ? (c.size === "giant" ? 11 : c.size === "subgiant" ? Math.min(11, R[c.type] + 1.5) : R[c.type]) : 7;
  const k = 32 / size;
  const label = title ?? (c ? `${c.type} ${c.size}${teff ? `, ${Math.round(teff)} K` : ""}` : "temperature unknown");
  return (
    <svg className={s.glyph} width={size} height={size} viewBox="0 0 32 32" role="img" aria-label={label}>
      <title>{label}</title>
      {c && c.size !== "dwarf" && <circle cx={16} cy={16} r={Math.min(15, r + 3.5)} fill="none" strokeWidth={STROKE * k} strokeDasharray={`${0.1 * k} ${2.4 * k}`} className={s.ink} />}
      <circle cx={16} cy={16} r={r} fill={fill} strokeWidth={STROKE * k} className={s.ink} />
      <path d={`M${16 - r * 0.55} ${16 - r * 0.2} A ${r * 0.62} ${r * 0.62} 0 0 1 ${16 - r * 0.1} ${16 - r * 0.6}`} fill="none" strokeWidth={STROKE * k * 0.8} className={s.ink} opacity={0.55} />
      {!c && <path d="M13.5 14.5c0-1.6 1.1-2.5 2.5-2.5s2.5.9 2.5 2.2c0 1.8-2.5 1.8-2.5 3.6M16 20.2v.1" fill="none" strokeWidth={STROKE * k} className={s.ink} />}
    </svg>
  );
}

/** A planet crossing its star, with the dip it makes drawn underneath: the mark for a candidate. */
export function TransitGlyph({ size = 36, title = "a planet crossing its star" }: { size?: number; title?: string }) {
  const k = 40 / size;
  return (
    <svg className={s.glyph} width={size} height={(size * 32) / 40} viewBox="0 0 40 32" {...(title ? { role: "img", "aria-label": title } : { "aria-hidden": true })}>
      {title && <title>{title}</title>}
      <circle cx={20} cy={12} r={9.5} fill="none" strokeWidth={STROKE * k} className={s.ink} />
      <path d="M6.5 15.2c4.5-1.3 9-2.1 13.4-2.5 4.5-.4 9-.1 13.6.7" fill="none" strokeWidth={STROKE * k * 0.8} strokeDasharray={`${1.2 * k} ${1.8 * k}`} className={s.ink} opacity={0.6} />
      <circle cx={22.5} cy={13.1} r={2.4} className={s.pen} />
      <path d="M3 27.6h10.8c1.1 0 1.6.2 2.2 1.4.5 1 1 1.3 2.4 1.3h3.2c1.4 0 1.9-.3 2.4-1.3.6-1.2 1.1-1.4 2.2-1.4H37" fill="none" strokeWidth={STROKE * k} className={s.ink} />
    </svg>
  );
}

/** TESS: four cameras in a row on the spacecraft bus, solar panels either side. For the data credit. */
export function TessGlyph({ size = 44, title = "the TESS spacecraft" }: { size?: number; title?: string }) {
  const k = 48 / size;
  const w = STROKE * k;
  return (
    <svg className={s.glyph} width={size} height={(size * 28) / 48} viewBox="0 0 48 28" role="img" aria-label={title}>
      <title>{title}</title>
      <path d="M13 20.5h22v4.2H13z" fill="none" strokeWidth={w} className={s.ink} strokeLinejoin="round" />
      {[15.4, 20.8, 26.2, 31.6].map((x) => (
        <g key={x}>
          <path d={`M${x - 1.9} 20.5 L${x - 2.4} 9.5 h4.8 L${x + 1.9} 20.5`} fill="none" strokeWidth={w} className={s.ink} strokeLinejoin="round" />
          <ellipse cx={x} cy={9.5} rx={2.4} ry={0.9} fill="none" strokeWidth={w * 0.8} className={s.ink} />
        </g>
      ))}
      <path d="M2 21.3h9.2v2.6H2zM36.8 21.3H46v2.6h-9.2z" fill="none" strokeWidth={w} className={s.ink} strokeLinejoin="round" />
      <path d="M5.1 21.3v2.6M8.1 21.3v2.6M39.9 21.3v2.6M42.9 21.3v2.6M11.2 22.6H13M35 22.6h1.8" fill="none" strokeWidth={w * 0.8} className={s.ink} />
    </svg>
  );
}

/** A strip of recorder paper with a flat trace and the pen still resting: nothing kept yet. */
export function EmptyTrace({ title = "A flat trace on recorder paper: the search has not kept a signal yet" }: { title?: string }) {
  // a deterministic, hand-looking noise line
  const pts: string[] = [];
  let y = 48;
  for (let i = 0; i <= 90; i++) {
    const x = 12 + i * 3.1;
    y = 48 + Math.sin(i * 1.7) * 2.2 + Math.sin(i * 0.53) * 1.4 + Math.cos(i * 3.1) * 1.1;
    pts.push(`${i ? "L" : "M"}${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  const penX = 12 + 90 * 3.1;
  return (
    <svg className={s.empty} viewBox="0 0 320 88" role="img" aria-label={title}>
      <title>{title}</title>
      {Array.from({ length: 11 }, (_, i) => (
        <path key={i} d={`M${12 + i * 29} 14V78`} className={i % 5 === 0 ? s.gridStrong : s.grid} />
      ))}
      <path d="M4 14H316M4 78H316" className={s.gridStrong} />
      <path d={pts.join("")} fill="none" strokeWidth={STROKE} className={s.ink} strokeLinejoin="round" />
      <circle cx={penX} cy={y} r={2.6} className={s.inkFill} />
      <path d={`M${penX} 14V78`} className={s.gridStrong} />
      {[60, 150, 240].map((x) => (
        <path key={x} d={`M${x - 4} 8h8l-4 5z`} fill="none" strokeWidth={STROKE} className={s.faint} strokeLinejoin="round" />
      ))}
    </svg>
  );
}

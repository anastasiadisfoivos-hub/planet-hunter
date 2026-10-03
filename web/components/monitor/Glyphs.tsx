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

// ---------- the icon set (DESIGN.md v3: Icons) ----------
// 24 px box, one 1.5 stroke, drawn by hand: coordinates are picked, not snapped, so lines keep a little of the pen.

export type IconName =
  | "monitor" | "candidates" | "log" | "methods"
  | "star" | "trace" | "pen" | "clock" | "sky" | "check" | "pixels" | "vote" | "catalogue" | "limits" | "step" | "honesty"
  | "day" | "night" | "replay" | "live";

const ICONS: Record<IconName, React.ReactNode> = {
  monitor: (
    <>
      <path d="M2.5 19.5h19M5.5 19.5v1.8M10.5 19.5v1.8M15.5 19.5v1.8M20.5 19.5v1.8" />
      <path d="M2.5 11.6h3.2l1.6-4.4 2.3 9.1 1.9-6.3 1.5 2.1h2.2" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={17.9} cy={12.1} r={1.6} className={s.inkFill} stroke="none" />
      <path d="M17.9 3.2v6.4" strokeDasharray="1 2" />
    </>
  ),
  candidates: (
    <>
      <circle cx={12} cy={9.6} r={6.6} />
      <circle cx={13.8} cy={10.4} r={1.9} className={s.pen} stroke="none" />
      <path d="M2.4 20.6h6.4c.9 0 1.2.3 1.6 1 .3.6.7.8 1.6.8s1.3-.2 1.6-.8c.4-.7.7-1 1.6-1h6.4" strokeLinecap="round" />
    </>
  ),
  log: (
    <>
      <path d="M2.5 5.5h5l1.2-1.8 1.3 3.4 1-1.6H21.5M2.5 12h8.2l1.1 2.6 1.2-1.4.8-1.2h8.2M2.5 18.5h3.8l1.1-1.5 1.4 2.4 1.2-.9h11.5" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  methods: (
    <>
      <path d="M5 2.8h13.6v18.4H5z" />
      <path d="M8.3 2.8v18.4" className={s.penStroke} />
      <path d="M10.8 7.4h5.4M10.8 11h5.4M10.8 14.6h3.6" />
    </>
  ),
  star: (
    <>
      <circle cx={12} cy={12} r={5.4} />
      <path d="M8.9 10.8a3.3 3.3 0 0 1 2.4-2.3" strokeLinecap="round" />
      <path d="M12 2.4v2.2M12 19.4v2.2M2.4 12h2.2M19.4 12h2.2M5.2 5.2l1.5 1.5M17.3 17.3l1.5 1.5M5.2 18.8l1.5-1.5M17.3 6.7l1.5-1.5" strokeLinecap="round" />
    </>
  ),
  trace: (
    <>
      <path d="M2.5 13.2h3l1.4-3.1 1.9 5.9 1.7-7.5 1.8 6.8 1.3-2.1h8.9" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M2.5 21h19" />
    </>
  ),
  pen: (
    <>
      <path d="M14.8 3.6l5.6 5.6-9.7 9.7-6.9 1.4 1.3-7z" strokeLinejoin="round" />
      <path d="M5.1 13.3l5.6 5.6M3.8 20.3l3.6-3.6" />
      <path d="M17.5 21h4" className={s.penStroke} />
    </>
  ),
  clock: (
    <>
      <circle cx={12} cy={12} r={8.6} />
      <path d="M12 6.8V12l3.6 2.2" strokeLinecap="round" />
      <path d="M12 3.4v1.1M20.6 12h-1.1M12 20.6v-1.1M3.4 12h1.1" />
    </>
  ),
  sky: (
    <>
      <ellipse cx={12} cy={12} rx={9.6} ry={6.2} />
      <path d="M12 5.8v12.4M7 6.9c-1.5 3.1-1.5 7.1 0 10.2M17 6.9c1.5 3.1 1.5 7.1 0 10.2M2.4 12h19.2" />
      <circle cx={15.4} cy={14.2} r={1.1} className={s.inkFill} stroke="none" />
    </>
  ),
  check: (
    <>
      <path d="M3.5 3.5h17v17h-17z" />
      <path d="M7.6 12.4l3 3.1 6-7.2" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  pixels: (
    <>
      <path d="M3 3h18v18H3zM9 3v18M15 3v18M3 9h18M3 15h18" />
      <path d="M9.6 9.6h4.8v4.8H9.6z" className={s.penFill} stroke="none" />
    </>
  ),
  vote: (
    <>
      <path d="M3.4 12.6h17.2v8.2H3.4z" />
      <path d="M8.8 12.6V4.2h6.4v8.4M7 12.6h10" />
      <path d="M10.6 8.3l1.2 1.3 1.9-2.5" strokeLinecap="round" strokeLinejoin="round" />
    </>
  ),
  catalogue: (
    <>
      <path d="M4 3.2h11.8l4.2 4.2v13.4H4z" />
      <path d="M15.8 3.2v4.2H20" />
      <path d="M7.4 11.4h9.2M7.4 14.6h9.2M7.4 17.8h5.8" />
      <path d="M7.4 7.6h3.4" className={s.knownStroke} strokeWidth={2.4} />
    </>
  ),
  limits: (
    <>
      <path d="M2.5 18.8h19M2.5 18.8V4" />
      <path d="M2.5 16.6c3.4-.4 5.4-2.6 7.2-6.3 1.7-3.4 3.6-5.2 7-5.5h4.8" strokeLinecap="round" />
      <path d="M13.8 3.4v15.4" strokeDasharray="1.2 2" className={s.penStroke} />
    </>
  ),
  step: (
    <>
      <path d="M2.8 20.6h5.4v-5.2h5.4v-5.2H19V4.8h2.2" strokeLinejoin="round" />
      <path d="M2.8 20.6h18.4" />
    </>
  ),
  honesty: (
    <>
      <circle cx={12} cy={11.4} r={7.4} strokeDasharray="2.2 1.9" />
      <path d="M9.6 9.4c0-1.5 1.1-2.4 2.4-2.4s2.4.8 2.4 2.1c0 1.7-2.4 1.7-2.4 3.5" strokeLinecap="round" />
      <path d="M12 15.2v.1" strokeLinecap="round" strokeWidth={2.2} />
    </>
  ),
  day: (
    <>
      <circle cx={12} cy={12} r={4.4} />
      <path d="M12 2.6v2.6M12 18.8v2.6M2.6 12h2.6M18.8 12h2.6M5.4 5.4l1.8 1.8M16.8 16.8l1.8 1.8M5.4 18.6l1.8-1.8M16.8 7.2l1.8-1.8" strokeLinecap="round" />
    </>
  ),
  night: (
    <>
      <path d="M15.6 3.6a8.6 8.6 0 1 0 4.8 13.7 7 7 0 0 1-4.8-13.7z" strokeLinejoin="round" />
      <path d="M17.6 6.4v2.2M16.5 7.5h2.2" strokeLinecap="round" />
    </>
  ),
  replay: (
    <>
      <path d="M4.2 12a7.8 7.8 0 1 0 2.3-5.5" strokeLinecap="round" />
      <path d="M6.1 2.9v3.9h3.9" strokeLinejoin="round" />
      <path d="M10.4 9.2v5.6l4.4-2.8z" className={s.inkFill} stroke="none" />
    </>
  ),
  live: (
    <>
      <circle cx={12} cy={12} r={2.6} className={s.penFill} stroke="none" />
      <path d="M7.4 7.4a6.5 6.5 0 0 0 0 9.2M16.6 7.4a6.5 6.5 0 0 1 0 9.2M4.6 4.6a10.4 10.4 0 0 0 0 14.8M19.4 4.6a10.4 10.4 0 0 1 0 14.8" strokeLinecap="round" />
    </>
  ),
};

/** One icon from the set. Decorative unless given a title (then it is an image with that name). */
export function Icon({ name, size = 22, title }: { name: IconName; size?: number; title?: string }) {
  return (
    <svg
      className={`${s.icon}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      strokeWidth={1.5}
      {...(title ? { role: "img", "aria-label": title } : { "aria-hidden": true, focusable: false })}
    >
      {title && <title>{title}</title>}
      <g className={s.ink} strokeLinecap="square">
        {ICONS[name]}
      </g>
    </svg>
  );
}

"use client";

// "Where is it": a 56° × 34° window of ESO's all-sky photograph around the event, with faint constellation lines and
// names, and the event as a ring in its category colour. The crop is pre-cut (scripts/build-sky.mjs); if it is
// missing (a live event the build has not seen), the same window is shown from the phone-size panorama.

import { useEffect, useState } from "react";
import { Info } from "@/components/picture/Info";
import type { Category } from "@/lib/contract";
import { CATEGORY_STYLE } from "@/lib/eventStyle";
import { constellationLabels, constellationPath, panoXY, windowAround, type LinesData, type NamesData } from "@/lib/galactic";
import { WHERE_SPAN } from "@/lib/pictureKeys";
import type { Pic } from "@/lib/pictures";
import s from "./gallery.module.css";

type Sky = { lines: LinesData; names: NamesData };
let skyData: Promise<Sky> | null = null;
const loadSky = () =>
  (skyData ??= Promise.all([
    fetch("/data/sky/constellation-lines.json").then((r) => r.json() as Promise<LinesData>),
    fetch("/data/sky/constellation-names.json").then((r) => r.json() as Promise<NamesData>),
  ]).then(([lines, names]) => ({ lines, names })));

// Everything is drawn in the frame of the 6000 × 3000 panorama the crops were cut from; the SVG scales with the picture.
const W = 6000;
const H = 3000;

type Props = { ra: number; dec: number; errorDeg: number; category: Category; constellation: string | null; crop: Pic | null; panorama: Pic };

export function CompactSky({ ra, dec, errorDeg, category, constellation, crop, panorama }: Props) {
  const [sky, setSky] = useState<Sky | null>(null);
  useEffect(() => {
    loadSky().then(setSky, () => undefined);
  }, []);

  const win = windowAround(ra, dec, WHERE_SPAN.l, WHERE_SPAN.b, W, H);
  const p = panoXY(ra, dec, W, H);
  // Horizontally the event is always centred; vertically the window is clamped at the poles.
  const ex = win.w / 2;
  const ey = p.y - win.y0;
  const r = Math.max(20, (errorDeg / 360) * W);
  const token = CATEGORY_STYLE[category].token;
  const fallback = crop
    ? undefined
    : {
        backgroundImage: `url(${panorama.src})`,
        backgroundSize: `${(W / win.w) * 100}% auto`,
        backgroundPosition: `${(-win.x0 / (win.w - W)) * 100}% ${(win.y0 / (H - win.h)) * 100}%`,
        backgroundRepeat: "repeat-x",
      };
  const where = constellation ? `In ${constellation}` : "Where it is";

  return (
    <figure className={s.where}>
      <div className={s.whereFrame} style={fallback} role="img" aria-label={`${where}, on ESO's photograph of the whole sky`}>
        {crop && (
          // eslint-disable-next-line @next/next/no-img-element -- a pre-cut, pre-sized crop; re-encoding it would only cost time
          <img src={crop.src} alt="" width={crop.width} height={crop.height} loading="lazy" decoding="async" />
        )}
        <svg viewBox={`0 0 ${Math.round(win.w)} ${Math.round(win.h)}`} preserveAspectRatio="xMidYMid slice" aria-hidden>
          {sky && <path className={s.whereLines} d={constellationPath(sky.lines, win)} />}
          {sky &&
            constellationLabels(sky.names, win).map((l) => (
              <text key={l.name} className={s.whereName} x={l.x} y={l.y} textAnchor="middle" fontSize={win.w / 36}>
                {l.name}
              </text>
            ))}
          <circle cx={ex} cy={ey} r={r} fill="none" stroke="var(--space)" strokeWidth={win.w / 110} />
          <circle cx={ex} cy={ey} r={r} fill="none" stroke={`var(${token})`} strokeWidth={win.w / 240} />
        </svg>
      </div>
      <figcaption className={s.capline}>
        <span className="cap">{where} · ESO/S. Brunier</span>
        <Info
          pic={crop ?? panorama}
          note="The whole-sky photograph, in galactic orientation: the Milky Way runs across. Constellation lines and names: d3-celestial (BSD-3-Clause)."
        />
      </figcaption>
    </figure>
  );
}

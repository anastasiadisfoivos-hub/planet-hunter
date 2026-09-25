"use client";

import { useEffect, useState } from "react";
import { formatLatLon } from "@/lib/format";
import s from "./map.module.css";

let land: Promise<{ d: string; viewBox: string }> | null = null;
function loadLand() {
  land ??= fetch("/data/land-110m.json").then((r) => r.json());
  return land;
}

/**
 * A small flat map of Earth (Natural Earth land outlines, equirectangular) with the event's location,
 * for events that happen at Earth rather than on the sky: fireballs, geomagnetic storms.
 */
export function EarthInset({ lat, lon, altKm, note }: { lat: number | null; lon: number | null; altKm: number | null; note?: string | null }) {
  const [path, setPath] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    loadLand().then((l) => live && setPath(l.d));
    return () => {
      live = false;
    };
  }, []);
  // No point given (a geomagnetic storm is planet-wide): show Earth without a marker, and say so.
  const at = lat != null && lon != null ? { x: lon + 180, y: 90 - lat, label: formatLatLon(lat, lon) } : null;
  return (
    <figure className={s.inset}>
      <svg viewBox="0 0 360 180" role="img" aria-label={at ? `Map of Earth marking ${at.label}` : "Map of Earth"}>
        <rect width="360" height="180" className={s.insetSea} />
        {[30, 60, 90, 120, 150].map((gy) => (
          <line key={gy} x1="0" x2="360" y1={gy} y2={gy} className={s.insetGrid} />
        ))}
        {path && <path d={path} className={s.insetLand} />}
        {at && (
          <g transform={`translate(${at.x} ${at.y})`} className={s.insetMark}>
            <circle r="7" className={s.insetRing} />
            <path d="M0 -4.2 L3.8 2.4 L-3.8 2.4 Z" />
          </g>
        )}
      </svg>
      <figcaption className={s.caption}>
        {at ? (
          <span className="mono">
            {at.label}
            {altKm != null ? `, ${altKm.toFixed(0)} km up` : ""}
          </span>
        ) : (
          <span>Worldwide: the source gives no single location for this event.</span>
        )}
        {note && <span className={s.note}>{note}</span>}
        <span className={s.credit}>Coastlines: Natural Earth (public domain)</span>
      </figcaption>
    </figure>
  );
}

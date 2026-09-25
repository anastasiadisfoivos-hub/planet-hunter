// The three ways in: Sky map, Lab, Planet finder. Each preview is drawn on the server from real data:
// the bright stars in their colours, the Lab's blackbody curves, and WASP-18's folded TESS light curve.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react/dist/ssr";
import type { SkyObjectsFile } from "@/lib/data";
import { bvToTeff, starColor } from "@/lib/starColor";
import { ThermoThumb } from "@/components/lab/Thumbs";
import s from "./home.module.css";

function readData<T>(file: string): T {
  return JSON.parse(readFileSync(join(process.cwd(), "public/data", file), "utf8")) as T;
}

const hex = ([r, g, b]: number[]) => `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)})`;

/** The whole sky on a Hammer projection: stars to magnitude 4, in their colours. */
function SkyThumb() {
  const W = 560;
  const H = 280;
  const { stars } = readData<SkyObjectsFile>("sky-objects.json");
  const dots: { x: number; y: number; r: number; o: number; c: string }[] = [];
  for (let i = 0; i < stars.ra.length; i++) {
    if (stars.mag[i] > 4) continue;
    let l = (stars.ra[i] > 180 ? stars.ra[i] - 360 : stars.ra[i]) * (Math.PI / 180);
    l = -l; // east to the left, as seen from Earth
    const b = stars.dec[i] * (Math.PI / 180);
    const z = Math.sqrt(1 + Math.cos(b) * Math.cos(l / 2));
    const x = (2 * Math.SQRT2 * Math.cos(b) * Math.sin(l / 2)) / z;
    const y = (Math.SQRT2 * Math.sin(b)) / z;
    dots.push({
      x: W / 2 + (x / (2 * Math.SQRT2)) * (W / 2 - 8),
      y: H / 2 - (y / Math.SQRT2) * (H / 2 - 8),
      r: Math.max(0.6, 2.2 - 0.38 * stars.mag[i]),
      o: Math.min(1, 1 - (stars.mag[i] + 1) / 7),
      c: hex(starColor(bvToTeff(stars.bv[i]))),
    });
  }
  return (
    <svg className={s.doorArt} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      <ellipse cx={W / 2} cy={H / 2} rx={W / 2 - 8} ry={H / 2 - 8} fill="none" stroke="var(--grid)" />
      <line x1={8} x2={W - 8} y1={H / 2} y2={H / 2} stroke="var(--grid)" />
      <line x1={W / 2} x2={W / 2} y1={8} y2={H - 8} stroke="var(--grid)" />
      {dots.map((d, i) => (
        <circle key={i} cx={d.x.toFixed(1)} cy={d.y.toFixed(1)} r={d.r.toFixed(2)} fill={d.c} fillOpacity={d.o.toFixed(2)} />
      ))}
    </svg>
  );
}

/** WASP-18's TESS light curve folded on its planet's orbit: the dip every candidate is judged on. */
function FinderThumb() {
  const W = 280;
  const H = 120;
  const r = readData<{ discoveries: { light_curve: { time_btjd: number[]; flux: number[] }; raw: { signal: { period: number; t0: number } } }[] }>(
    "lab/wasp-18.result.json",
  );
  const { light_curve: lc, raw } = r.discoveries[0];
  const { period, t0 } = raw.signal;
  const span = 0.16;
  const pts: [number, number][] = [];
  lc.time_btjd.forEach((t, i) => {
    let p = (((t - t0) / period) % 1 + 1) % 1;
    if (p > 0.5) p -= 1;
    if (Math.abs(p) <= span) pts.push([p, lc.flux[i]]);
  });
  const hi = 1.004;
  const lo = 0.986;
  const x = (p: number) => 12 + ((p + span) / (2 * span)) * (W - 24);
  const y = (f: number) => 14 + ((hi - Math.min(hi, Math.max(lo, f))) / (hi - lo)) * (H - 28);
  return (
    <svg className={s.doorArt} viewBox={`0 0 ${W} ${H}`} aria-hidden>
      {pts.map(([p, f], i) => (
        <circle key={i} cx={x(p).toFixed(1)} cy={y(f).toFixed(1)} r={1.1} fill="var(--ink-secondary)" fillOpacity={0.55} />
      ))}
      <line x1={x(0)} x2={x(0)} y1={8} y2={H - 8} stroke="var(--accent)" strokeWidth={1} strokeDasharray="3 3" />
    </svg>
  );
}

export function Doors() {
  return (
    <section className={s.doors} aria-labelledby="doors-title">
      <h2 id="doors-title" className={s.h2}>
        Three ways in
      </h2>
      <div className={s.doorGrid}>
        <Link href="/map" className={`${s.door} ${s.doorMap}`}>
          <SkyThumb />
          <span className={s.doorText}>
            <span className={s.doorTitle}>
              Sky map <ArrowRight size={16} aria-hidden />
            </span>
            <span className={s.doorLine}>This week&apos;s events at their real places on a 3D sky.</span>
            <span className={s.doorDo}>Turn the sky, filter by kind of event, and open one to see its pictures and who reported it.</span>
          </span>
        </Link>
        <Link href="/lab" className={s.door}>
          <ThermoThumb />
          <span className={s.doorText}>
            <span className={s.doorTitle}>
              Lab <ArrowRight size={16} aria-hidden />
            </span>
            <span className={s.doorLine}>Small experiments on real stars.</span>
            <span className={s.doorDo}>Take a star&apos;s temperature, hear its light as sound, rebuild Hubble&apos;s diagram and read chemical fingerprints.</span>
          </span>
        </Link>
        <Link href="/finder" className={s.door}>
          <FinderThumb />
          <span className={s.doorText}>
            <span className={s.doorTitle}>
              Planet finder <ArrowRight size={16} aria-hidden />
            </span>
            <span className={s.doorLine}>Real planet candidates from our nightly search.</span>
            <span className={s.doorDo}>Look at the dip in each star&apos;s light and judge for yourself whether it looks like a planet.</span>
          </span>
        </Link>
      </div>
    </section>
  );
}

// Four well-known planet systems, each opening its star's lab page. Numbers come from the same
// NASA Exoplanet Archive files the Lab uses (hosts.json and lab/star-lab.mock.json), read at build time.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import Link from "next/link";
import type { HostsFile } from "@/lib/data";
import { starColor } from "@/lib/starColor";
import s from "./home.module.css";

type Planet = [string, number | null, number | null, number | null, number | null]; // name, period_d, a_au, radius_earth, mass_earth
type LabFile = { stars: Record<string, { planets: Planet[] }> };

const LY_PER_PC = 3.26156;
const EARTH_PER_JUPITER_MASS = 317.83;

const nf = (n: number, digits = 0) => n.toLocaleString("en-GB", { maximumFractionDigits: digits, minimumFractionDigits: digits });
const hours = (days: number) => nf(days * 24, 1);

/** One plain fact per star. Where it quotes a number, the number is from the archive. */
const FACTS: Record<string, (p: Planet[]) => string> = {
  "WASP-18": (p) =>
    `Its planet has about ${nf((p[0][4] ?? 0) / EARTH_PER_JUPITER_MASS)} times Jupiter's mass and goes round the star every ${hours(p[0][1] ?? 0)} hours.`,
  "WASP-121": (p) => `A year on WASP-121 b lasts ${hours(p[0][1] ?? 0)} hours. Its day side is hot enough to turn metals into gas.`,
  "WASP-43": (p) => `WASP-43 b circles its cool orange star every ${hours(p[0][1] ?? 0)} hours, closer in than almost any other giant planet.`,
  "TOI-700": (p) => {
    const d = p.find((x) => x[0] === "TOI-700 d");
    return `${p.length} known planets. TOI-700 d is ${nf(d?.[3] ?? 0, 1)} times Earth's width and orbits where liquid water could exist.`;
  },
};

export function KnownSystems() {
  const read = <T,>(f: string) => JSON.parse(readFileSync(join(process.cwd(), "public/data", f), "utf8")) as T;
  const hosts = read<HostsFile>("hosts.json");
  const lab = read<LabFile>("lab/star-lab.mock.json");

  const systems = Object.keys(FACTS)
    .map((name) => {
      const i = hosts.name.indexOf(name);
      if (i < 0) return null;
      const tic = hosts.tic[i];
      const planets = lab.stars[tic]?.planets ?? [];
      const [r, g, b] = starColor(hosts.teff[i]);
      return {
        name,
        tic,
        teff: hosts.teff[i],
        radius: hosts.rad[i],
        ly: hosts.dist[i] * LY_PER_PC,
        color: `rgb(${Math.round(r * 255)} ${Math.round(g * 255)} ${Math.round(b * 255)})`,
        fact: planets.length ? FACTS[name](planets) : null,
      };
    })
    .filter((x) => x !== null);

  return (
    <section className={s.known} aria-labelledby="known-title">
      <h2 id="known-title" className={s.h2}>
        Start with a famous star
      </h2>
      <ul className={s.knownList}>
        {systems.map((x) => (
          <li key={x.tic}>
            <Link href={`/lab/star/${x.tic}`} className={s.knownCard}>
              <span className={s.knownTop}>
                <span
                  className={s.swatch}
                  // Colour from the star's temperature, size from its radius (the Sun would be 28 px).
                  style={{ background: x.color, width: Math.max(10, x.radius * 28), height: Math.max(10, x.radius * 28) }}
                  aria-hidden
                />
                <span className={s.knownName}>
                  {x.name}
                  <span className="label">TIC {x.tic}</span>
                </span>
              </span>
              {x.fact && <span className={s.knownFact}>{x.fact}</span>}
              <span className={s.knownMeta}>
                <span className="mono">{nf(x.teff)} K</span>
                <span><span className="mono">{nf(x.radius, 2)}</span> × the Sun&apos;s width</span>
                <span className="mono">{nf(x.ly)} light-years</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

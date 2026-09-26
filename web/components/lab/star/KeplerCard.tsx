"use client";

import { useState, type CSSProperties } from "react";
import { Info } from "@phosphor-icons/react";
import { Button, Segmented } from "@/components/ui";
import type { KnownPlanet, StarLab } from "@/lib/api";
import { Note, nf0 } from "../chart";
import { useWidth } from "../hooks";
import { rgbCss, temperatureColor } from "../physics";
import { DAYS_PER_YEAR, keplerAu } from "../transit";
import { Card } from "./Card";
import type { StarMass } from "./shared";
import s from "./star.module.css";
import l from "../lab.module.css";

const A_MIN = 0.005;
const A_MAX = 50;
const STEPS = 1000;
const toA = (v: number) => A_MIN * (A_MAX / A_MIN) ** (v / STEPS);
const toV = (a: number) => Math.round((STEPS * Math.log(a / A_MIN)) / Math.log(A_MAX / A_MIN));

/** A planet's year in hours, days or years, never scientific notation. */
const fmtYear = (P: number) => (P < 2 ? `${(P * 24).toFixed(1)} h` : P < 1000 ? `${P.toFixed(2)} d` : `${(P / DAYS_PER_YEAR).toFixed(1)} yr`);

const fmtAu = (a: number) => (a >= 10 ? a.toFixed(1) : a >= 1 ? a.toFixed(2) : a >= 0.1 ? a.toFixed(3) : a.toFixed(4));
const REFS = [
  { name: "Mercury", a: 0.387 },
  { name: "Earth", a: 1 },
  { name: "Jupiter", a: 5.2 },
];

function offBy(guess: number, truth: number): string {
  const r = guess / truth;
  if (Math.abs(r - 1) < 0.05) return "Within 5% of the real orbit.";
  return r > 1 ? `${r < 2 ? `${Math.round((r - 1) * 100)}%` : `${r.toFixed(1)}×`} too big.` : `${r > 0.5 ? `${Math.round((1 - r) * 100)}%` : `${(1 / r).toFixed(1)}×`} too small.`;
}

function Orbits({ guess, truth, teff }: { guess: number; truth: number | null; teff: number | null }) {
  const [ref, w] = useWidth<HTMLDivElement>();
  const size = Math.min(w, 320);
  const c = size / 2;
  const rMax = Math.max(guess, truth ?? 0) * 1.12;
  const px = (a: number) => (a / rMax) * (c - 8);
  const refs = REFS.filter((r) => r.a < rMax && px(r.a) > 10);
  return (
    <div ref={ref}>
      <svg className={l.svg} width={size} height={size} style={{ margin: "0 auto" }} role="img" aria-label={`Orbits to scale: your guess ${fmtAu(guess)} AU${truth ? `, the real orbit ${fmtAu(truth)} AU` : ""}.`}>
        {refs.map((r) => (
          <g key={r.name}>
            <circle cx={c} cy={c} r={px(r.a)} fill="none" stroke="var(--grid)" strokeWidth={1} />
            <text className={l.axis} x={c} y={c - px(r.a) - 4} textAnchor="middle">
              {r.name}
            </text>
          </g>
        ))}
        <circle cx={c} cy={c} r={px(guess)} fill="none" stroke="var(--ink)" strokeWidth={2} strokeDasharray="5 4" />
        {truth != null && <circle cx={c} cy={c} r={px(truth)} fill="none" stroke="var(--ink)" strokeWidth={2} />}
        <circle cx={c} cy={c} r={4} fill={teff ? rgbCss(temperatureColor(teff)) : "var(--ink)"} />
      </svg>
      <ul className={l.legend} style={{ justifyContent: "center" }}>
        <li>
          <span className={`${l.keyLine} ${l.keyDash}`} style={{ borderTopColor: "var(--ink)" }} aria-hidden />
          Your guess
        </li>
        {truth != null && (
          <li>
            <span className={l.keyLine} aria-hidden />
            Real orbit
          </li>
        )}
        <li>To scale; orbits drawn as circles</li>
      </ul>
    </div>
  );
}

function Check({ lab, planet, mass }: { lab: StarLab; planet: KnownPlanet & { period_d: number }; mass: StarMass }) {
  const [guess, setGuess] = useState(1);
  const [shown, setShown] = useState(false);
  const P = planet.period_d;
  const years = P / DAYS_PER_YEAR;
  const kepler = keplerAu(mass.value, P);
  const truth = planet.a_au ?? kepler;
  const track = { "--track": `linear-gradient(90deg, var(--ink) ${(toV(guess) / STEPS) * 100}%, var(--control-border) 0)` } as CSSProperties;
  return (
    <div className={l.bench}>
      <div className={l.chartBox}>
        <div className={l.chartHead}>
          <h3 className={l.h3}>{planet.name}&apos;s orbit</h3>
        </div>
        <Orbits guess={guess} truth={shown ? truth : null} teff={lab.teff} />
      </div>
      <div className={l.side}>
        <div className={l.block}>
          <dl className={l.readout}>
            <div>
              <dt className="label">Its year</dt>
              <dd>{fmtYear(P)}</dd>
            </div>
            <div>
              <dt className="label">{years < 1 ? "Orbits per Earth year" : "In Earth years"}</dt>
              <dd>{years < 1 ? nf0.format(DAYS_PER_YEAR / P) : years.toFixed(2)}</dd>
            </div>
            <div className={l.readoutWide}>
              <dt className="label">Star&apos;s mass</dt>
              <dd>
                {mass.value.toFixed(2)} Suns<span className={s.valueNote}>{mass.estimated ? "Estimated from its temperature" : "NASA Exoplanet Archive"}</span>
              </dd>
            </div>
          </dl>
          <p className={l.body}>
            Kepler&apos;s third law: <strong>a = ∛(M × P²)</strong>, with a in AU, M in Suns and P in years. Earth: ∛(1 × 1²) = 1 AU.
          </p>
        </div>
        <div className={l.block}>
          <label className={l.field}>
            <span className={l.fieldHead}>
              <span className="label">Your guess, orbit size</span>
              <span className={s.sliderValue}>{fmtAu(guess)} AU</span>
            </span>
            <input
              className={l.range}
              style={track}
              type="range"
              min={0}
              max={STEPS}
              value={toV(guess)}
              onChange={(e) => {
                setGuess(toA(Number(e.target.value)));
                setShown(false);
              }}
              aria-valuetext={`${fmtAu(guess)} astronomical units`}
            />
            <span className={`${l.scaleLabels} mono ${l.help}`}>
              <span>0.005 AU</span>
              <span>50 AU</span>
            </span>
          </label>
          {!shown ? (
            <div>
              <Button onClick={() => setShown(true)}>Reveal the real orbit</Button>
            </div>
          ) : (
            <div aria-live="polite" className={l.stage}>
              <dl className={s.compare}>
                <div className={s.yours}>
                  <dt>Your guess</dt>
                  <dd>{fmtAu(guess)} AU</dd>
                </div>
                <div>
                  <dt>
                    Kepler&apos;s law
                    <span className={s.valueNote}>
                      ∛({mass.value.toFixed(2)} × ({fmtYear(P)} ÷ 1 yr)²)
                    </span>
                  </dt>
                  <dd>{fmtAu(kepler)} AU</dd>
                </div>
                <div>
                  <dt>
                    NASA archive
                    <span className={s.valueNote}>measured orbit</span>
                  </dt>
                  <dd>{planet.a_au != null ? `${fmtAu(planet.a_au)} AU` : "not listed"}</dd>
                </div>
              </dl>
              <p className={l.body}>
                <strong>{offBy(guess, truth)}</strong>{" "}
                {planet.a_au != null
                  ? Math.abs(kepler / planet.a_au - 1) < 0.05
                    ? `Kepler's law lands within ${Math.max(1, Math.round(Math.abs(kepler / planet.a_au - 1) * 100))}% of the archive; the rest is rounding in the star's mass${mass.estimated ? ", which here is only an estimate" : ""} and the two numbers coming from different studies.`
                    : `Kepler's law and the archive differ by ${Math.round(Math.abs(kepler / planet.a_au - 1) * 100)}%: ${mass.estimated ? "this star's mass is only estimated from its temperature" : "the mass and orbit in the archive come from different studies"}.`
                  : "The archive lists no measured orbit for this planet, so Kepler's law is the answer."}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function KeplerCard({ lab, mass }: { lab: StarLab; mass: StarMass | null }) {
  const planets = lab.known_planets.filter((p): p is KnownPlanet & { period_d: number } => p.period_d != null && p.period_d > 0);
  const [pick, setPick] = useState(planets[0]?.name ?? "");
  const lede = "From a planet's year and its star's mass, predict how far out it orbits. Then check.";
  if (!planets.length || !mass) {
    return (
      <Card
        id="kepler"
        title="Kepler check"
        lede={lede}
        locked={!mass ? "No mass or temperature is listed for this star, so there is nothing to weigh the orbit with." : "None of its known planets has a measured year."}
      />
    );
  }
  const planet = planets.find((p) => p.name === pick) ?? planets[0];
  return (
    <Card id="kepler" title="Kepler check" data={mass.estimated ? "estimate" : "real"} lede={lede}>
      {planets.length > 1 &&
        (planets.length <= 4 ? (
          <div>
            <Segmented label="Planet" value={planet.name} onChange={setPick} options={planets.map((p) => ({ value: p.name, label: p.name }))} />
          </div>
        ) : (
          <label className={l.field} style={{ maxWidth: 320 }}>
            <span className="label">Planet</span>
            <select className={l.select} value={planet.name} onChange={(e) => setPick(e.target.value)}>
              {planets.map((p) => (
                <option key={p.name}>{p.name}</option>
              ))}
            </select>
          </label>
        ))}
      <Check key={planet.name} lab={lab} planet={planet} mass={mass} />
      <Note icon={<Info size={14} aria-hidden />}>
        Heavier stars pull harder, so a planet with the same year sits farther out. The law leaves out the planet&apos;s own mass, which matters
        only for the heaviest planets. Years and orbits: NASA Exoplanet Archive.
      </Note>
    </Card>
  );
}

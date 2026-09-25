// Small previews for the Lab index, drawn on the server from the same maths and data as each experiment.

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { blackbodyCurve, distanceMpc, rgbCss, speedKms, temperatureColor, wavelengthRgb } from "./physics";
import s from "./lab.module.css";

const W = 280;
const H = 120;

function readData<T>(file: string): T {
  return JSON.parse(readFileSync(join(process.cwd(), "public/data/lab", file), "utf8")) as T;
}

function Frame({ children, label }: { children: React.ReactNode; label: string }) {
  return (
    <svg className={s.thumb} viewBox={`0 0 ${W} ${H}`} aria-hidden data-label={label}>
      {children}
    </svg>
  );
}

export function ThermoThumb() {
  const temps = [3200, 5772, 12000];
  return (
    <Frame label="Three blackbody curves: red, white and blue stars">
      {temps.map((t) => {
        const c = blackbodyCurve(t, 1, 2000, 120);
        const d = c.nm.map((nm, i) => `${i ? "L" : "M"}${(16 + (nm / 2000) * (W - 32)).toFixed(1)},${(H - 16 - c.value[i] * (H - 36)).toFixed(1)}`).join("");
        return <path key={t} d={d} fill="none" stroke={rgbCss(temperatureColor(t))} strokeWidth={2} />;
      })}
    </Frame>
  );
}

export function HearThumb() {
  const r = readData<{ discoveries: { light_curve: { time_btjd: number[]; flux: number[] } }[] }>("wasp-18.result.json");
  const { time_btjd: t, flux: f } = r.discoveries[0].light_curve;
  const n = Math.min(t.length, 330); // about a week
  const lo = Math.min(...f.slice(0, n));
  const hi = Math.max(...f.slice(0, n));
  const d = Array.from({ length: n }, (_, i) => `${i ? "L" : "M"}${(12 + ((t[i] - t[0]) / (t[n - 1] - t[0])) * (W - 24)).toFixed(1)},${(20 + ((hi - f[i]) / (hi - lo)) * (H - 40)).toFixed(1)}`).join("");
  return (
    <Frame label="Seven days of WASP-18's brightness, with regular dips">
      <path d={d} fill="none" stroke="var(--ink-secondary)" strokeWidth={1} />
      <line x1={W * 0.62} x2={W * 0.62} y1={12} y2={H - 12} stroke="var(--accent)" strokeWidth={2} />
    </Frame>
  );
}

export function HubbleThumb() {
  const h = readData<{ abs_mag: number; supernovae: { z: number; peak_mag: number }[] }>("hubble.demo.json");
  const x = (d: number) => 16 + (d / 450) * (W - 32);
  const y = (v: number) => H - 14 - (v / 31000) * (H - 28);
  return (
    <Frame label="Demo supernovae: farther ones move away faster">
      <line x1={x(0)} y1={y(0)} x2={x(430)} y2={y(70 * 430)} stroke="var(--accent)" strokeWidth={1.5} />
      {h.supernovae.map((sn) => (
        <circle key={sn.z} cx={x(distanceMpc(sn.peak_mag, h.abs_mag))} cy={y(speedKms(sn.z))} r={2.6} fill="var(--supernova)" />
      ))}
    </Frame>
  );
}

export function FingerprintThumb() {
  const lines = [656.28, 486.13, 434.05, 410.17, 588.99, 589.59, 518.36, 517.27, 516.73, 527.04, 430.79, 393.37, 396.85];
  const x = (nm: number) => ((nm - 380) / 370) * W;
  const stops = Array.from({ length: 19 }, (_, i) => 380 + i * 20);
  return (
    <Frame label="A rainbow crossed by dark absorption lines">
      <defs>
        <linearGradient id="thumb-rb" x1="0" x2={W} y1="0" y2="0" gradientUnits="userSpaceOnUse">
          {stops.map((nm) => (
            <stop key={nm} offset={(nm - 380) / 370} stopColor={rgbCss(wavelengthRgb(nm))} />
          ))}
        </linearGradient>
      </defs>
      <rect x={0} y={36} width={W} height={48} fill="url(#thumb-rb)" />
      {lines.map((nm) => (
        <rect key={nm} x={x(nm) - 1.2} y={36} width={2.4} height={48} fill="var(--space)" />
      ))}
    </Frame>
  );
}

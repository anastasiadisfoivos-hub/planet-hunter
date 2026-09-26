// Builds the Lab's DEMO files in public/data/lab/: the Hubble-diagram supernovae and stand-ins for
// the SPECTRA session's files (same shapes as web/public/data/spectra/). Run from web/:
//   node components/lab/data/build-mocks.mjs
// Everything here is made up to exercise the UI, except the atomic line wavelengths (air, nm, NIST ASD).
// Deterministic: same output every run.

import { mkdirSync, writeFileSync } from "node:fs";

const OUT = "public/data/lab";
const MOCK = `${OUT}/spectra-mock`;
mkdirSync(`${MOCK}/stars`, { recursive: true });
mkdirSync(`${MOCK}/planets`, { recursive: true });

let seed = 20260925;
const rnd = () => (seed = (seed * 16807) % 2147483647) / 2147483647;
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
const r = (v, d) => Number(v.toFixed(d));
const write = (path, obj) => writeFileSync(path, JSON.stringify(obj) + "\n");

// ---------- Hubble diagram: 30 nearby type Ia supernovae in a 70 km/s/Mpc universe ----------
{
  const H0 = 70;
  const M = -19.3;
  const c = 299792.458;
  const sn = [];
  for (let i = 0; i < 30; i++) {
    const z = 0.008 * (0.1 / 0.008) ** ((i + rnd() * 0.8) / 30);
    const d = (c * z) / H0;
    const m = M + 25 + 5 * Math.log10(d) + gauss() * 0.14;
    sn.push({ name: `Demo SN ${String(i + 1).padStart(2, "0")}`, z: r(z, 4), peak_mag: r(m, 2) });
  }
  sn.sort((a, b) => a.z - b.z);
  write(`${OUT}/hubble.demo.json`, {
    demo: true,
    note: "Made-up supernovae: redshifts spread from 0.008 to 0.1, peak magnitudes from a 70 km/s/Mpc universe with a type Ia peak of -19.3 mag and 0.14 mag of scatter. Live TNS supernovae replace this later.",
    abs_mag: M,
    supernovae: sn,
  });
}

// ---------- elements.json: [{symbol, name, lines:[{nm, relative_intensity}]}] ----------
const ELEMENTS = [
  { symbol: "H", name: "Hydrogen", lines: [[656.28, 1], [486.13, 0.36], [434.05, 0.18], [410.17, 0.1], [397.01, 0.06]] },
  { symbol: "He", name: "Helium", lines: [[587.56, 1], [447.15, 0.4], [501.57, 0.3], [667.82, 0.35], [706.52, 0.25], [492.19, 0.12], [471.31, 0.08], [402.62, 0.1]] },
  { symbol: "Na", name: "Sodium", lines: [[588.99, 1], [589.59, 0.5], [568.82, 0.05], [498.28, 0.03]] },
  { symbol: "Ca", name: "Calcium", lines: [[393.37, 1], [396.85, 0.9], [422.67, 0.5], [445.48, 0.1], [616.22, 0.12], [643.91, 0.1], [849.8, 0.3], [854.21, 0.45], [866.21, 0.35]] },
  { symbol: "Fe", name: "Iron", lines: [[404.58, 0.6], [406.36, 0.4], [430.79, 0.5], [438.35, 0.7], [440.48, 0.45], [495.76, 0.35], [516.89, 0.3], [526.95, 0.45], [527.04, 0.4], [532.8, 0.5], [537.15, 0.35], [617.33, 0.12], [649.5, 0.15]] },
  { symbol: "Mg", name: "Magnesium", lines: [[516.73, 0.7], [517.27, 0.85], [518.36, 1], [383.83, 0.5], [457.11, 0.15], [880.68, 0.3]] },
  { symbol: "O", name: "Oxygen", lines: [[777.19, 1], [777.42, 0.85], [777.54, 0.7], [844.64, 0.6], [615.82, 0.15], [557.73, 0.2], [630.03, 0.25]] },
  { symbol: "K", name: "Potassium", lines: [[766.49, 1], [769.9, 0.6], [404.41, 0.08]] },
  { symbol: "Li", name: "Lithium", lines: [[670.78, 1], [610.35, 0.2], [460.29, 0.05]] },
];
write(
  `${MOCK}/elements.json`,
  ELEMENTS.map((e) => ({ symbol: e.symbol, name: e.name, lines: e.lines.map(([nm, ri]) => ({ nm, relative_intensity: ri })) })),
);

// ---------- sun_spectrum.json: a 5772 K blackbody with the strong Fraunhofer lines cut in ----------
{
  const planck = (nm, t) => {
    const x = 1.438777e7 / (nm * t);
    return 1 / nm ** 5 / Math.expm1(x);
  };
  const LINES = [
    [393.37, "Ca", "K", 0.9, 1.2],
    [396.85, "Ca", "H", 0.85, 1.1],
    [410.17, "H", "h (H-delta)", 0.5, 0.4],
    [430.79, "Fe", "G", 0.5, 0.35],
    [434.05, "H", "H-gamma", 0.55, 0.45],
    [438.35, "Fe", "d", 0.45, 0.2],
    [486.13, "H", "F (H-beta)", 0.65, 0.5],
    [495.76, "Fe", "", 0.3, 0.12],
    [516.73, "Mg", "b4", 0.45, 0.2],
    [517.27, "Mg", "b2", 0.55, 0.22],
    [518.36, "Mg", "b1", 0.6, 0.24],
    [526.95, "Fe", "E2", 0.4, 0.15],
    [532.8, "Fe", "", 0.3, 0.12],
    [588.99, "Na", "D2", 0.75, 0.18],
    [589.59, "Na", "D1", 0.7, 0.18],
    [616.22, "Ca", "", 0.3, 0.12],
    [656.28, "H", "C (H-alpha)", 0.7, 0.45],
    // Telluric: oxygen in Earth's air, not the Sun.
    [686.7, "O2", "B", 0.55, 0.6],
    [759.4, "O2", "A", 0.7, 1],
  ];
  const wl = [];
  const flux = [];
  const peak = planck(502, 5772);
  for (let nm = 380; nm <= 780.0001; nm += 0.25) {
    let f = planck(nm, 5772) / peak;
    for (const [c, , , depth, w] of LINES) f *= 1 - depth * Math.exp(-0.5 * ((nm - c) / w) ** 2);
    // Thousands of weak lines, as a gentle ripple.
    f *= 1 - 0.04 * rnd() * (nm < 500 ? 2 : 1);
    wl.push(r(nm, 2));
    flux.push(r(f, 4));
  }
  write(`${MOCK}/sun_spectrum.json`, {
    wavelength_nm: wl,
    flux,
    lines: LINES.map(([nm, element, label]) => ({ nm, element, label, origin: element === "O2" || element === "H2O" ? "earth_atmosphere" : "sun" })),
    source: "DEMO: a 5772 K blackbody with the strong Fraunhofer lines drawn in",
    credit: "Demo data; the real solar atlas arrives with the SPECTRA files",
  });
}

// ---------- stars/<tic>.abundances.json and stars/<tic>.gaia_xp.json ----------
const STARS = [
  { tic: 100100827, name: "WASP-18", teff: 6400, base: 0.1 },
  { tic: 22529346, name: "WASP-121", teff: 6600, base: 0.13 },
  { tic: 181949561, name: "WASP-39", teff: 5400, base: 0.0 },
];
for (const s of STARS) {
  const els = ["Fe", "Mg", "Si", "Ca", "Na", "O", "C", "Ni", "Ti"];
  write(`${MOCK}/stars/${s.tic}.abundances.json`, {
    tic: s.tic,
    name: s.name,
    source: "DEMO: made-up abundances",
    elements: els.map((symbol, i) => ({
      symbol,
      x_h_dex: r(s.base + gauss() * 0.08, 2),
      err_dex: i === 6 ? null : r(0.04 + rnd() * 0.06, 2),
    })),
  });
  const wl = [];
  const fl = [];
  for (let i = 0; i < 343; i++) {
    const nm = 336 + (i * (1020 - 336)) / 342;
    const x = 1.438777e7 / (nm * s.teff);
    wl.push(r(nm, 1));
    fl.push(r((1e-17 / (nm / 1000) ** 5 / Math.expm1(x)) * (1 + 0.02 * gauss()), 22));
  }
  write(`${MOCK}/stars/${s.tic}.gaia_xp.json`, {
    tic: s.tic,
    wavelength_nm: wl,
    flux: fl,
    source: "DEMO: a smooth blackbody shaped like a Gaia XP sampled spectrum",
    credit: "Demo data: a stand-in spectrum, not a measurement",
  });
}

// ---------- planets/<slug>.atmosphere.json ----------
{
  const wl = [];
  const depth = [];
  const err = [];
  for (let i = 0; i < 28; i++) {
    const um = 0.82 + i * 0.033;
    const water = 380 * Math.exp(-0.5 * ((um - 1.4) / 0.09) ** 2) + 160 * Math.exp(-0.5 * ((um - 1.15) / 0.05) ** 2);
    wl.push(r(um, 3));
    depth.push(Math.round(14700 + water + gauss() * 45));
    err.push(Math.round(40 + rnd() * 25));
  }
  const DEMO_REF = "Demo data: a placeholder reference";
  write(`${MOCK}/planets/wasp-121-b.atmosphere.json`, {
    planet: "WASP-121 b",
    detections: ["H2O", "Fe", "Mg", "Ca", "Na", "V"].map((species) => ({ species, reference: DEMO_REF })),
    spectrum: { wavelength_um: wl, depth_ppm: depth, err_ppm: err },
    source: "DEMO: made-up transmission spectrum",
  });
  write(`${MOCK}/planets/wasp-18-b.atmosphere.json`, {
    planet: "WASP-18 b",
    detections: ["H2O", "CO"].map((species) => ({ species, reference: DEMO_REF })),
    spectrum: null,
    source: "DEMO: made-up detections",
  });
  write(`${MOCK}/planets/wasp-39-b.atmosphere.json`, {
    planet: "WASP-39 b",
    detections: ["CO2", "H2O", "SO2", "Na", "K"].map((species) => ({ species, reference: DEMO_REF })),
    spectrum: {
      wavelength_um: wl.map((w) => r(w * 3, 3)),
      depth_ppm: depth.map((d, i) => d + 6800 + Math.round(900 * Math.exp(-0.5 * ((wl[i] * 3 - 4.3) / 0.15) ** 2))),
      err_ppm: err,
    },
    source: "DEMO: made-up transmission spectrum",
  });
}

console.log("wrote Lab demo files to", OUT);

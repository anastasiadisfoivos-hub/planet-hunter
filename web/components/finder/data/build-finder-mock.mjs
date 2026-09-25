// Builds the Finder's DEMO data: public/data/finder/*. Run from web/: node components/finder/data/build-finder-mock.mjs
//
// Shapes follow the HUNT session's Candidate and the PIXELS session's PixelVet exactly. What is made up:
// the candidates themselves (TIC numbers, periods, depths, checks, scores, votes, funnel counts, the
// injection-recovery grid) and their light curves, which are simulated transits plus white noise.
// What is real: the pixel images. They are copied from two real PIXELS runs (pixels-*.json here):
// WASP-18 sector 104 (the dip is on the target) and TOI-4257 sector 62 (the dip is on a neighbour).
// Three candidates sit on real planet hosts from hosts.json, so "Open star lab" and "Fly to it" work.

import { mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

const here = path.dirname(new URL(import.meta.url).pathname);
const out = path.resolve(here, "../../../public/data/finder");

// ---------- seeded randomness ----------
function mulberry32(a) {
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rand = mulberry32(20260926);
const gauss = () => {
  const u = 1 - rand();
  const v = rand();
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
};
const r = (x, nd) => Number(x.toFixed(nd));

// ---------- constants ----------
const RJUP_PER_RSUN = 9.731;
const CADENCE_D = 30 / 1440; // light curves are binned to 30 minutes
const SECTOR_D = 27.4;
const sectorStart = (s) => 1325.3 + (s - 1) * 27.28; // BTJD, close to TESS's real sector starts

// ---------- the candidates ----------
// kind: planet-like | vshape | oddeven | depthchange | fewdips | secondary
// verdict: which pixel result to attach.
const SPECS = [
  { tic: 219345170, period: 3.8127, depth: 1840, dur: 2.9, snr: 31.4, rs: 0.94, sectors: [81, 82], kind: "planet-like", verdict: "on target", votes: [41, 6, 9] },
  { tic: 1003831, host: true, period: 11.2064, depth: 620, dur: 3.6, snr: 14.8, rs: 1.07, sectors: [92, 93], kind: "planet-like", verdict: "on target", votes: [12, 2, 7] },
  { tic: 307809773, period: 1.6352, depth: 410, dur: 1.4, snr: 12.1, rs: 0.61, sectors: [88], kind: "planet-like", verdict: "on target", votes: [3, 1, 2] },
  { tic: 459837008, period: 6.0419, depth: 5230, dur: 2.2, snr: 44.9, rs: 1.21, sectors: [84, 85, 86], kind: "vshape", verdict: "possible neighbour", votes: [8, 19, 11] },
  { tic: 1129033, host: true, period: 5.7331, depth: 290, dur: 2.5, snr: 9.6, rs: 0.91, sectors: [95], kind: "planet-like", verdict: "possible neighbour", votes: [2, 1, 3] },
  { tic: 88863718, period: 2.2186, depth: 8900, dur: 1.9, snr: 58.2, rs: 0.83, sectors: [90, 91], kind: "oddeven", verdict: "on target", votes: [6, 22, 4] },
  { tic: 150428135, period: 17.9412, depth: 1270, dur: 5.1, snr: 16.3, rs: 1.34, sectors: [87, 88, 89], kind: "planet-like", verdict: "on target", votes: [9, 1, 3] },
  { tic: 278683844, period: 4.4501, depth: 2410, dur: 2.7, snr: 21.7, rs: 1.02, sectors: [83], kind: "depthchange", verdict: "off target", votes: [1, 14, 5] },
  { tic: 1167538, host: true, period: 8.8763, depth: 740, dur: 3.3, snr: 11.9, rs: 0.98, sectors: [96], kind: "planet-like", verdict: "inconclusive", votes: [0, 0, 1] },
  { tic: 356016119, period: 9.1406, depth: 3050, dur: 3.7, snr: 18.4, rs: 1.46, sectors: [94], kind: "fewdips", verdict: "inconclusive", votes: [2, 3, 6] },
  { tic: 29781292, period: 0.7784, depth: 520, dur: 1.1, snr: 17.2, rs: 0.72, sectors: [86, 87], kind: "planet-like", verdict: "on target", votes: [5, 2, 1] },
  { tic: 393831507, period: 3.0927, depth: 14200, dur: 2.4, snr: 73.5, rs: 1.12, sectors: [97], kind: "secondary", verdict: "off target", votes: [0, 4, 1] },
  { tic: 257060897, period: 7.3355, depth: 980, dur: 3.1, snr: 13.3, rs: 0.87, sectors: [89, 90], kind: "planet-like", verdict: "possible neighbour", votes: [4, 3, 2] },
  { tic: 441462736, period: 2.7918, depth: 360, dur: 1.8, snr: 8.4, rs: 0.79, sectors: [98], kind: "planet-like", verdict: "on target", votes: [0, 0, 0] },
];

const hosts = JSON.parse(readFileSync(path.resolve(here, "../../../public/data/hosts.json"), "utf8"));
const hostName = (tic) => {
  const i = hosts.tic.indexOf(tic);
  return i >= 0 ? hosts.name[i] : null;
};

// ---------- light curves ----------
/** Trapezoid transit: fraction of depth at time offset dt (days) from mid-transit. */
function shape(dt, durD, ingressFrac) {
  const half = durD / 2;
  const a = Math.abs(dt);
  if (a >= half) return 0;
  const ing = Math.max(ingressFrac * durD, 1e-6);
  return a <= half - ing ? 1 : (half - a) / ing;
}

function lightcurve(spec, t0) {
  const durD = spec.dur / 24;
  const ingress = spec.kind === "vshape" ? 0.5 : spec.kind === "secondary" ? 0.3 : 0.14;
  const dRel = spec.depth / 1e6;
  const time = [];
  for (const s of spec.sectors) {
    const start = sectorStart(s);
    for (let t = start; t < start + SECTOR_D; t += CADENCE_D) {
      if (t > start + 13.2 && t < start + 14.4) continue; // the mid-sector data downlink gap
      time.push(t);
    }
  }
  // Count in-transit points to set the noise so the fold reaches the stated SNR.
  const inT = time.filter((t) => {
    const ph = (((t - t0) / spec.period) % 1 + 1) % 1;
    return Math.min(ph, 1 - ph) * spec.period < durD / 2;
  }).length;
  const sigma = (dRel * Math.sqrt(Math.max(inT, 1))) / spec.snr;
  const flux = time.map((t, k) => {
    const n = Math.round((t - t0) / spec.period);
    const dt = t - (t0 + n * spec.period);
    let depth = dRel;
    if (spec.kind === "oddeven" && n % 2 !== 0) depth *= 0.62;
    if (spec.kind === "depthchange") depth *= spec.sectors.length > 1 && t > sectorStart(spec.sectors[1]) ? 0.55 : 1 + 0.25 * Math.sin(n);
    let f = 1 - depth * shape(dt, durD, ingress);
    if (spec.kind === "secondary") {
      const dt2 = t - (t0 + (n + 0.5) * spec.period);
      f -= dRel * 0.18 * shape(dt2, durD, ingress);
    }
    // a slow wiggle left over after detrending, plus white noise
    f += sigma * 0.25 * Math.sin((k / 211) * Math.PI) + sigma * gauss();
    return f;
  });
  const phase = time.map((t) => {
    const p = (((t - t0) / spec.period) % 1 + 1) % 1;
    return p >= 0.5 ? p - 1 : p;
  });
  const order = phase.map((_, k) => k).sort((a, b) => phase[a] - phase[b]);
  return {
    unfolded: { time_btjd: time.map((t) => r(t, 4)), flux: flux.map((f) => r(f, 6)) },
    folded: { phase: order.map((k) => r(phase[k], 5)), flux: order.map((k) => r(flux[k], 6)) },
    nTransits: new Set(time.map((t) => Math.round((t - t0) / spec.period)).filter((n) => {
      const mid = t0 + n * spec.period;
      return time.some((t) => Math.abs(t - mid) < durD / 2);
    })).size,
  };
}

// ---------- checks (names and wording follow hunter/vet.py; two extra that HUNT plans) ----------
function checks(spec, radius, nTr) {
  const d = spec.depth / 1e6;
  const pct = (x) => (x * 100).toFixed(3);
  const out = [];
  out.push({ name: "snr", value: spec.snr, passed: true, reason: `The dip stands ${Math.round(spec.snr)} times above the noise over ${nTr} events.` });
  if (spec.kind === "oddeven") {
    out.push({ name: "odd_even", value: 4.6, passed: false, reason: `Alternate dips have different depths (${pct(d)}% vs ${pct(d * 0.62)}%, 4.6 sigma apart). A planet makes identical dips; two stars eclipsing each other usually do not, so the true period is likely ${(2 * spec.period).toFixed(4)} days.` });
  } else {
    const ns = r(0.3 + rand() * 1.6, 2);
    out.push({ name: "odd_even", value: ns, passed: true, reason: `Alternate dips have matching depths (${pct(d * (1 + 0.01 * gauss()))}% vs ${pct(d * (1 + 0.01 * gauss()))}%), as expected for a planet.` });
  }
  if (spec.kind === "secondary") {
    out.push({ name: "secondary_eclipse", value: 11.8, passed: false, reason: `There is a second, shallower dip at phase 0.50 (${pct(d * 0.18)}% deep, 18% of the main dip). A dip that big halfway round the orbit means the companion gives off a lot of light itself, like a star does.` });
  } else {
    out.push({ name: "secondary_eclipse", value: r(rand() * 2.4, 2), passed: true, reason: "Halfway round the orbit there is no significant dip, consistent with a planet." });
  }
  const note = `Depth ${pct(d)}% on a star ${spec.rs.toFixed(2)} times the Sun's size gives ${radius.best.toFixed(2)} Jupiter radii (likely ${radius.low.toFixed(2)} to ${radius.high.toFixed(2)}).`;
  out.push({ name: "size", value: r(radius.best, 3), passed: true, reason: `${note} That is within the size range of planets.` });
  if (spec.kind === "fewdips") {
    out.push({ name: "transit_count", value: nTr, passed: null, reason: `Only ${nTr} dips were caught, the minimum the search accepts. The period could be a multiple of the true one; this check can't decide with so few.` });
  } else {
    out.push({ name: "transit_count", value: nTr, passed: true, reason: `${nTr} separate dips line up on the same period.` });
  }
  if (spec.kind === "depthchange") {
    out.push({ name: "depth_consistency", value: 3.9, passed: false, reason: "The dip is about half as deep in the second sector as in the first (3.9 sigma). A planet's dip keeps its depth; light from a neighbour that leaks in by different amounts in each sector does not." });
  } else {
    out.push({ name: "depth_consistency", value: r(rand() * 1.8, 2), passed: true, reason: spec.sectors.length > 1 ? "The dip has the same depth in every sector." : "One sector only, and the dips within it agree in depth." });
  }
  return out;
}

// ---------- pixels ----------
const w18 = JSON.parse(readFileSync(path.join(here, "pixels-wasp18-s0104.json"), "utf8"));
const toi = JSON.parse(readFileSync(path.join(here, "pixels-toi4257-s0062.json"), "utf8"));

function trimMarkers(img) {
  const [h, w] = img.shape;
  return img.markers
    .filter((m) => m.kind === "target" || (m.x > -0.5 && m.x < w - 0.5 && m.y > -0.5 && m.y < h - 0.5 && m.gmag < 17.5))
    .map((m) => ({ ...m, needed_depth: m.needed_depth ?? null }));
}

function images(img, tic, overrides = {}) {
  return {
    sector: img.sector,
    pixel_scale_arcsec: img.pixel_scale_arcsec,
    compass: img.compass,
    out_of_transit: img.out_of_transit,
    difference: overrides.difference ?? img.difference,
    markers: trimMarkers(img).map((m) => (m.kind === "target" ? { ...m, label: `TIC ${tic}` } : m)),
    centroid: overrides.centroid === undefined ? { x: img.centroid.x, y: img.centroid.y } : overrides.centroid,
    borrowed_from: overrides.from,
  };
}

function pixelVet(spec) {
  const src = spec.verdict === "off target" ? toi : w18;
  const from = src === toi ? "TOI-4257 (TIC 75208638), TESS sector 62" : "WASP-18 (TIC 100100827), TESS sector 104";
  if (spec.verdict === "on target") {
    const off = r(0.3 + rand() * 1.6, 2);
    const sig = r(0.3 + rand() * 1.2, 2);
    return {
      verdict: "on target",
      reason: `the light lost in transit comes from the target (offset ${off.toFixed(1)}″ = ${(off / 21).toFixed(2)} px, ${sig.toFixed(1)}σ) and every Gaia neighbour able to mimic the dip is excluded by the centroid`,
      on_target_probability: r(0.93 + rand() * 0.06, 3),
      centroid_offset_arcsec: off,
      offset_sigma: sig,
      suspect_neighbours: [],
      images: images(w18, spec.tic, { from }),
    };
  }
  if (spec.verdict === "possible neighbour") {
    const m = w18.markers[1];
    const sep = r(Math.hypot(m.x - w18.markers[0].x, m.y - w18.markers[0].y) * w18.pixel_scale_arcsec, 1);
    const need = r(Math.min(0.9, (spec.depth / 1e6) * (8 + rand() * 30)), 4);
    return {
      verdict: "possible neighbour",
      reason: `the centroid is consistent with the target (1.4σ, 3.2″) but cannot rule out neighbours close enough to share it: Gaia DR3 ${m.gaia_id} (G=${m.gmag.toFixed(1)}, ${sep.toFixed(0)}″ away) would need a ${(need * 100).toFixed(1)}% eclipse`,
      on_target_probability: r(0.48 + rand() * 0.3, 3),
      centroid_offset_arcsec: 3.2,
      offset_sigma: 1.4,
      suspect_neighbours: [{ gaia_id: m.gaia_id, sep_arcsec: sep, gmag: m.gmag, needed_depth: need }],
      images: images(w18, spec.tic, { from }),
    };
  }
  if (spec.verdict === "off target") {
    return {
      verdict: "off target",
      reason: "the light lost in transit comes from 24.9″ (1.25 px) away from the target, 22.7σ off; it matches Gaia DR3 5423774792624492928 (G=14.3, 25″ away), which would need a 3.4% eclipse (centroid 0.8σ from it)",
      on_target_probability: 0,
      centroid_offset_arcsec: 24.94,
      offset_sigma: 22.69,
      suspect_neighbours: [{ gaia_id: "5423774792624492928", sep_arcsec: 25.0, gmag: 14.322, needed_depth: 0.03351 }],
      images: images(toi, spec.tic, { from }),
    };
  }
  // inconclusive: the dip is too shallow to show up in the pixels. Real out-of-transit image, noise-only difference.
  const [h, w] = w18.shape;
  const noise = Array.from({ length: h }, () => Array.from({ length: w }, () => r(0.06 * gauss(), 4)));
  return {
    verdict: "inconclusive",
    reason: "the dip is not visible in the pixels (best difference-image SNR 2.1 < 5 over 1 sector(s)), so its source cannot be located",
    on_target_probability: null,
    centroid_offset_arcsec: null,
    offset_sigma: null,
    suspect_neighbours: [],
    images: images(w18, spec.tic, { from: `${from}, with the difference image replaced by noise`, difference: noise, centroid: null }),
  };
}

// ---------- score (0 to 1, four parts) ----------
function score(spec, cks, pv) {
  const signal = Math.min(1, Math.log10(spec.snr) / Math.log10(80)) * 0.35;
  const shapeP = (spec.kind === "vshape" ? 0.25 : spec.kind === "secondary" ? 0.4 : 0.85 + rand() * 0.15) * 0.2;
  const passedN = cks.filter((c) => c.passed === true).length;
  const failedN = cks.filter((c) => c.passed === false).length;
  const checksP = Math.max(0, (passedN / cks.length) * 0.25 - failedN * 0.1);
  const pixels = (pv.on_target_probability ?? 0.35) * 0.2;
  const parts = { signal: r(signal, 3), shape: r(shapeP, 3), checks: r(checksP, 3), pixels: r(pixels, 3) };
  return { score: r(signal + shapeP + checksP + pixels, 3), parts };
}

// ---------- build ----------
rmSync(out, { recursive: true, force: true });
mkdirSync(path.join(out, "c"), { recursive: true });

const rows = [];
const created0 = Date.parse("2026-09-18T04:10:00Z");
SPECS.forEach((spec, k) => {
  const t0 = r(sectorStart(spec.sectors[0]) + 0.3 + rand() * spec.period, 5);
  const lc = lightcurve(spec, t0);
  const best = Math.sqrt(spec.depth / 1e6) * spec.rs * RJUP_PER_RSUN;
  const radius = { best, low: best * (0.86 - rand() * 0.04), high: best * (1.14 + rand() * 0.05) };
  const cks = checks(spec, radius, lc.nTransits);
  const pv = pixelVet(spec);
  const { score: sc, parts } = score(spec, cks, pv);
  const name = spec.host ? hostName(spec.tic) : null;
  const id = `tic${spec.tic}-01`;
  const created_at = new Date(created0 + k * 13.7 * 3600e3).toISOString().replace(".000Z", "Z");
  const candidate = {
    id,
    tic: spec.tic,
    name,
    period_d: spec.period,
    t0_btjd: t0,
    duration_h: spec.dur,
    depth_ppm: spec.depth,
    snr: spec.snr,
    sde: r(spec.snr * (0.62 + rand() * 0.2), 1),
    n_transits: lc.nTransits,
    sectors: spec.sectors,
    radius_rjup: r(radius.best, 3),
    radius_low: r(radius.low, 3),
    radius_high: r(radius.high, 3),
    checks: cks,
    score: sc,
    score_parts: parts,
    known_lists: { confirmed: false, toi: false, ctoi: false, eb: false },
    folded: lc.folded,
    unfolded: lc.unfolded,
    created_at,
  };
  const [planet, fake, unsure] = spec.votes;
  const votes = { planet, fake, unsure, my_vote: null };
  writeFileSync(path.join(out, "c", `${id}.json`), JSON.stringify({ candidate, pixels: pv, votes }));
  const summary = Object.fromEntries(Object.entries(candidate).filter(([k]) => !["folded", "unfolded", "checks"].includes(k)));
  rows.push({ ...summary, checks_passed: cks.filter((c) => c.passed === true).length, checks_total: cks.length, pixel_verdict: pv.verdict, votes });
});

const funnel = [
  { key: "stars", label: "Stars searched", count: 48213 },
  { key: "signals", label: "Repeating dips found", count: 2906 },
  { key: "checks", label: "Passed the checks", count: 412 },
  { key: "unlisted", label: "Not on any list we checked", count: 61 },
  { key: "pixels", label: "Pixel check done", count: 58 },
  { key: "candidates", label: "Candidates to review", count: rows.length },
];

writeFileSync(
  path.join(out, "index.mock.json"),
  JSON.stringify({
    meta: {
      demo: true,
      note: "Made-up candidates with simulated light curves; pixel images borrowed from real PIXELS runs on WASP-18 and TOI-4257.",
      run_at: "2026-09-25T03:00:00Z",
      funnel,
    },
    candidates: rows.sort((a, b) => b.score - a.score),
  }),
);

// ---------- injection-recovery grid ----------
// A simple stand-in model: recovery rises with the SNR a planet of that size and period would reach in
// ~1.6 sectors around a Sun-like star, and needs at least three dips.
const radiusEdges = [0.5, 1, 1.5, 2, 3, 4, 6, 8, 11, 16, 22];
const periodEdges = [0.5, 1, 2, 4, 7, 10, 14, 20, 30];
const recovery = [];
const injected = [];
for (let i = 0; i < radiusEdges.length - 1; i++) {
  const rowR = [];
  const rowN = [];
  const rE = Math.sqrt(radiusEdges[i] * radiusEdges[i + 1]);
  for (let j = 0; j < periodEdges.length - 1; j++) {
    const P = Math.sqrt(periodEdges[j] * periodEdges[j + 1]);
    const depth = (rE / 109.1) ** 2;
    const nTr = (1.6 * SECTOR_D) / P;
    const durH = 13 * (P / 365) ** (1 / 3);
    const snr = (depth / 900e-6) * Math.sqrt(nTr * durH * 2);
    let p = 1 / (1 + Math.exp(-(snr - 9) / 1.8));
    p *= nTr >= 3 ? 1 : nTr >= 2 ? 0.25 : 0.02;
    p *= 0.97;
    const n = 180 + Math.round(rand() * 60);
    const rec = Math.round(n * Math.min(1, Math.max(0, p * (1 + 0.03 * gauss()))));
    rowR.push(r((100 * rec) / n, 1));
    rowN.push(n);
  }
  recovery.push(rowR);
  injected.push(rowN);
}
writeFileSync(
  path.join(out, "sensitivity.mock.json"),
  JSON.stringify({
    demo: true,
    run_at: "2026-09-21T02:00:00Z",
    stars_used: 2000,
    radius_edges_rearth: radiusEdges,
    period_edges_d: periodEdges,
    recovery_pct: recovery,
    n_injected: injected,
  }),
);

console.log(`wrote ${rows.length} candidates, index, sensitivity to ${path.relative(process.cwd(), out)}`);

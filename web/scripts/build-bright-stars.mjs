// Build web/public/data/bright-stars.json: names and distances for the bright catalogue stars in
// sky-objects.json (Yale BSC positions), matched by position to the HYG database v4.1 (astronexus,
// CC BY-SA 4.0; https://github.com/astronexus/HYG-Database), which carries Hipparcos distances,
// IAU proper names, Bayer/Flamsteed designations and luminosities.
//
//   node web/scripts/build-bright-stars.mjs <path to hygdata_v41.csv>
//
// Output arrays are index-aligned with sky-objects.json stars. Radius is NOT catalogued for these
// stars: it is estimated from luminosity and temperature (R = sqrt(L) (5772 K / T)^2) and the app says so.

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const data = path.join(here, "..", "public", "data");
const hygPath = process.argv[2];
if (!hygPath) throw new Error("usage: node build-bright-stars.mjs <hygdata_v41.csv>");

const GREEK = {
  Alp: "α", Bet: "β", Gam: "γ", Del: "δ", Eps: "ε", Zet: "ζ", Eta: "η", The: "θ", Iot: "ι", Kap: "κ", Lam: "λ", Mu: "μ",
  Nu: "ν", Xi: "ξ", Omi: "ο", Pi: "π", Rho: "ρ", Sig: "σ", Tau: "τ", Ups: "υ", Phi: "φ", Chi: "χ", Psi: "ψ", Ome: "ω",
};

function parseCsvLine(line) {
  const out = [];
  let cur = "";
  let q = false;
  for (const ch of line) {
    if (ch === '"') q = !q;
    else if (ch === "," && !q) {
      out.push(cur);
      cur = "";
    } else cur += ch;
  }
  out.push(cur);
  return out;
}

const text = await readFile(hygPath, "utf8");
const lines = text.split("\n").filter(Boolean);
const head = parseCsvLine(lines[0]);
const col = Object.fromEntries(head.map((h, i) => [h, i]));
// Only stars bright enough to be in the BSC (V < 7) matter; bucket them by declination for matching.
const hyg = [];
for (let i = 1; i < lines.length; i++) {
  const r = parseCsvLine(lines[i]);
  const mag = Number(r[col.mag]);
  if (!(mag < 7.2) || r[col.proper] === "Sol") continue;
  hyg.push({
    ra: Number(r[col.ra]) * 15,
    dec: Number(r[col.dec]),
    mag,
    proper: r[col.proper],
    bayer: r[col.bayer],
    flam: r[col.flam],
    con: r[col.con],
    hr: r[col.hr],
    hd: r[col.hd],
    hip: r[col.hip],
    dist: Number(r[col.dist]),
    lum: Number(r[col.lum]),
    spect: r[col.spect],
  });
}
const bucket = new Map();
for (const s of hyg) {
  const k = Math.floor(s.dec);
  if (!bucket.has(k)) bucket.set(k, []);
  bucket.get(k).push(s);
}

const sky = JSON.parse(await readFile(path.join(data, "sky-objects.json"), "utf8"));
const hosts = JSON.parse(await readFile(path.join(data, "hosts.json"), "utf8"));
const DEG = Math.PI / 180;
const sep = (ra1, d1, ra2, d2) => {
  const c = Math.sin(d1 * DEG) * Math.sin(d2 * DEG) + Math.cos(d1 * DEG) * Math.cos(d2 * DEG) * Math.cos((ra1 - ra2) * DEG);
  return Math.acos(Math.min(1, Math.max(-1, c))) / DEG;
};

function nameOf(s) {
  if (s.proper) return s.proper;
  if (s.bayer && s.con) return `${GREEK[s.bayer.replace(/-?\d+$/, "")] ?? s.bayer}${/\d+$/.test(s.bayer) ? s.bayer.match(/\d+$/)[0] : ""} ${s.con}`;
  if (s.flam && s.con) return `${s.flam} ${s.con}`;
  if (s.hr) return `HR ${s.hr}`;
  if (s.hd) return `HD ${s.hd}`;
  return null;
}

const st = sky.stars;
const n = st.ra.length;
const out = { source: "HYG database v4.1 (astronexus, CC BY-SA 4.0), matched by position to the Yale BSC", name: [], dist: [], lum: [], hip: [], host: [] };
let matched = 0;
let named = 0;
for (let i = 0; i < n; i++) {
  let best = null;
  let bestScore = Infinity;
  for (let k = Math.floor(st.dec[i]) - 1; k <= Math.floor(st.dec[i]) + 1; k++) {
    for (const s of bucket.get(k) ?? []) {
      const d = sep(st.ra[i], st.dec[i], s.ra, s.dec);
      if (d > 0.06) continue;
      const score = d / 0.06 + Math.abs(s.mag - st.mag[i]);
      if (Math.abs(s.mag - st.mag[i]) < 0.8 && score < bestScore) {
        bestScore = score;
        best = s;
      }
    }
  }
  const nm = best ? nameOf(best) : null;
  if (best) matched++;
  if (nm) named++;
  out.name.push(nm ?? "");
  // HYG uses 100000 pc for "no parallax".
  out.dist.push(best && best.dist > 0 && best.dist < 99999 ? Math.round(best.dist * 100) / 100 : 0);
  out.lum.push(best && best.lum > 0 ? Number(best.lum.toPrecision(4)) : 0);
  out.hip.push(best?.hip ? Number(best.hip) : 0);
  // A known planet host at the same spot (within 20 arcseconds).
  let host = -1;
  for (let h = 0; h < hosts.count; h++) {
    if (Math.abs(hosts.dec[h] - st.dec[i]) > 0.01) continue;
    if (sep(hosts.ra[h], hosts.dec[h], st.ra[i], st.dec[i]) < 20 / 3600) host = h;
  }
  out.host.push(host);
}
await writeFile(path.join(data, "bright-stars.json"), JSON.stringify(out));
console.log(`bright stars: ${n}, matched ${matched}, named ${named}, also planet hosts ${out.host.filter((h) => h >= 0).length}`);

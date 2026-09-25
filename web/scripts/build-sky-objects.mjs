// Build web/public/data/sky-objects.json: real positions and sizes for the illustrated sky.
//
//   node web/scripts/build-sky-objects.mjs
//
// All catalogues come from VizieR (CDS, Strasbourg). See web/CREDITS.md.
//   VII/20   Sharpless (1959), HII regions                -> emission nebulae
//   VII/216  Rodgers, Campbell & Whiteoak (1960), HII     -> southern emission nebulae
//   VII/7A   Lynds (1962), dark nebulae                    -> dark clouds
//   VII/272  Green (2009), Galactic supernova remnants     -> SNR filaments
//   V/50     Yale Bright Star Catalogue, 5th ed.           -> naked-eye stars
// Plus a short hand list of famous objects (positions from SIMBAD) that the catalogues above
// miss or undersize: Carina, Tarantula, Coalsack, Gum, several reflection nebulae.

import { writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, "..", "public", "data", "sky-objects.json");

const VIZ = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv";

async function vizier(source, columns, extra = "") {
  const url = `${VIZ}?-source=${source}&-out=${columns.join(",")}&-out.max=unlimited&-oc.form=d${extra}`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${source}: HTTP ${res.status}`);
  const text = await res.text();
  const lines = text.split("\n").filter((l) => l && !l.startsWith("#"));
  // header, units, dashes, then data
  const header = lines[0].split("\t").map((h) => h.trim());
  return lines.slice(3).map((l) => {
    const cells = l.split("\t");
    return Object.fromEntries(header.map((h, i) => [h, (cells[i] ?? "").trim()]));
  });
}

const num = (v) => (v === "" || v === undefined ? NaN : Number(v));
const r3 = (v) => Math.round(v * 1000) / 1000;

// type codes shared with the shader: 0 emission, 1 reflection, 2 dark, 3 supernova remnant
const EMISSION = 0;
const REFLECTION = 1;
const DARK = 2;
const SNR = 3;

// [name, ra, dec, radius_deg, type, brightness 0..1]
const FAMOUS = [
  ["Orion Nebula (M42)", 83.822, -5.391, 0.55, EMISSION, 1],
  ["Carina Nebula (NGC 3372)", 161.265, -59.867, 1.1, EMISSION, 1],
  ["Lagoon Nebula (M8)", 270.904, -24.387, 0.7, EMISSION, 0.95],
  ["Eagle Nebula (M16)", 274.7, -13.807, 0.35, EMISSION, 0.8],
  ["Trifid Nebula (M20)", 270.6, -23.03, 0.2, EMISSION, 0.7],
  ["Tarantula Nebula (30 Dor)", 84.676, -69.101, 0.4, EMISSION, 1],
  ["Rosette Nebula", 97.98, 4.95, 0.7, EMISSION, 0.7],
  ["North America Nebula", 314.75, 44.33, 1.2, EMISSION, 0.6],
  ["Gum Nebula", 128.0, -43.0, 16, EMISSION, 0.12],
  ["Pleiades reflection nebula", 56.75, 24.12, 0.6, REFLECTION, 0.8],
  ["Rho Ophiuchi cloud", 246.4, -23.4, 2.2, REFLECTION, 0.55],
  ["Witch Head Nebula (IC 2118)", 76.9, -7.2, 1.2, REFLECTION, 0.4],
  ["M78", 86.69, 0.08, 0.15, REFLECTION, 0.6],
  ["Iris Nebula (NGC 7023)", 315.4, 68.17, 0.15, REFLECTION, 0.5],
  ["Coalsack", 192.9, -62.9, 3.4, DARK, 0.9],
  ["Horsehead (B33)", 85.25, -2.46, 0.08, DARK, 1],
  ["Pipe Nebula", 258.8, -27.0, 3.0, DARK, 0.7],
];

async function main() {
  const [sh, rcw, ldn, snr, bsc] = await Promise.all([
    vizier("VII/20/catalog", ["Sh2", "_RAJ2000", "_DEJ2000", "Diam", "Bright"]),
    vizier("VII/216/rcw", ["RCW", "_RA.icrs", "_DE.icrs", "MajAxis", "MinAxis", "Br"]),
    vizier("VII/7A/ldn", ["LDN", "_RA.icrs", "_DE.icrs", "Area", "Opacity"]),
    vizier("VII/272/snrs", ["SNR", "_RAJ2000", "_DEJ2000", "Dmaj", "Dmin", "Names"]),
    vizier("V/50/catalog", ["HR", "_RAJ2000", "_DEJ2000", "Vmag", "B-V"], "&Vmag=<6.2"),
  ]);

  /** @type {Array<[number, number, number, number, number]>} ra, dec, radius, type, brightness */
  const nebulae = [];
  const push = (ra, dec, r, type, b) => {
    if (!Number.isFinite(ra) || !Number.isFinite(dec) || !(r > 0)) return;
    nebulae.push([r3(ra), r3(dec), r3(r), type, Math.round(b * 100) / 100]);
  };

  for (const f of FAMOUS) push(f[1], f[2], f[3], f[4], f[5]);
  const famousNear = (ra, dec, r) =>
    FAMOUS.some(([, fra, fdec, fr]) => Math.hypot((ra - fra) * Math.cos((dec * Math.PI) / 180), dec - fdec) < Math.max(fr, r) * 0.6);

  let counts = { sharpless: 0, rcw: 0, lynds: 0, snr: 0 };
  for (const row of sh) {
    const ra = num(row._RAJ2000), dec = num(row._DEJ2000), r = num(row.Diam) / 120;
    if (famousNear(ra, dec, r)) continue;
    push(ra, dec, Math.max(r, 0.05), EMISSION, 0.25 + 0.2 * (num(row.Bright) || 1));
    counts.sharpless++;
  }
  for (const row of rcw) {
    const ra = parseAngle(row["_RA.icrs"], true), dec = parseAngle(row["_DE.icrs"], false);
    // Sharpless already covers the sky north of -27; RCW fills in the south.
    if (!(dec < -27)) continue;
    const r = (num(row.MajAxis) + (num(row.MinAxis) || num(row.MajAxis))) / 240;
    if (famousNear(ra, dec, r)) continue;
    const br = row.Br?.startsWith("b") ? 0.8 : row.Br?.startsWith("m") ? 0.55 : 0.35;
    push(ra, dec, Math.max(r, 0.05), EMISSION, br);
    counts.rcw++;
  }
  for (const row of ldn) {
    const opacity = num(row.Opacity), area = num(row.Area);
    // Only the darkest, largest clouds: the rest vanish at map scale.
    if (!(opacity >= 4 && area >= 0.25)) continue;
    push(parseAngle(row["_RA.icrs"], true), parseAngle(row["_DE.icrs"], false), Math.sqrt(area / Math.PI), DARK, 0.3 + 0.1 * (opacity - 3));
    counts.lynds++;
  }
  for (const row of snr) {
    const d = (num(row.Dmaj) + (num(row.Dmin) || num(row.Dmaj))) / 2;
    if (!(d >= 20)) continue;
    // VII/272 gives sexagesimal RA/Dec even with -oc.form=d in some mirrors: handle both.
    const ra = parseAngle(row._RAJ2000, true), dec = parseAngle(row._DEJ2000, false);
    push(ra, dec, d / 120, SNR, Math.min(1, 0.35 + d / 400));
    counts.snr++;
  }

  const stars = { ra: [], dec: [], mag: [], bv: [] };
  for (const row of bsc) {
    const ra = num(row._RAJ2000), dec = num(row._DEJ2000), v = num(row.Vmag);
    if (!Number.isFinite(ra) || !Number.isFinite(v)) continue;
    stars.ra.push(r3(ra));
    stars.dec.push(r3(dec));
    stars.mag.push(Math.round(v * 100) / 100);
    stars.bv.push(Number.isFinite(num(row["B-V"])) ? Math.round(num(row["B-V"]) * 100) / 100 : 0.6);
  }

  const json = JSON.stringify({
    generated_at: new Date().toISOString().slice(0, 19) + "Z",
    note: "Positions and sizes are real (catalogues below). Nebula shapes drawn from them are illustrations.",
    sources: {
      nebulae: "VizieR VII/20 (Sharpless 1959), VII/216 (RCW 1960), VII/7A (Lynds 1962), VII/272 (Green 2009), plus SIMBAD positions for a few famous objects",
      stars: "VizieR V/50, Yale Bright Star Catalogue 5th ed. (Hoffleit & Warren 1991), V < 6.2",
    },
    nebula_columns: ["ra_deg", "dec_deg", "radius_deg", "type (0 emission, 1 reflection, 2 dark, 3 SNR)", "brightness"],
    nebulae,
    stars,
  });
  await writeFile(out, json);
  console.log(
    `nebulae: ${nebulae.length} (famous ${FAMOUS.length}, sharpless ${counts.sharpless}, rcw ${counts.rcw}, lynds ${counts.lynds}, snr ${counts.snr}); stars: ${stars.ra.length}`,
  );
  console.log(`sky-objects.json ${json.length} B raw, ${gzipSync(json).length} B gzip`);
}

function parseAngle(v, isRa) {
  if (v === undefined || v === "") return NaN;
  if (!/\s|:/.test(v)) return Number(v);
  const parts = v.split(/[\s:]+/).map(Number);
  const sign = v.trim().startsWith("-") ? -1 : 1;
  const [a, b = 0, c = 0] = parts.map(Math.abs);
  const deg = a + b / 60 + c / 3600;
  return isRa ? deg * 15 : sign * deg;
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

// Build web/public/data/hosts.json: known planet host stars from the NASA Exoplanet Archive
// (Planetary Systems Composite Parameters, `pscomppars`), keeping only hosts inside the Rubin
// survey footprint built by rubin_footprint.py.
//
//   node web/scripts/build-hosts.mjs
//
// Distances are the archive's `sy_dist`. For almost every host that value comes from TICv8
// (Stassun et al. 2019), whose distances are Gaia DR2 parallax distances (Bailer-Jones et al. 2018).
// The per-host reference is kept as `dist_ref`.

import { readFile, writeFile } from "node:fs/promises";
import { gzipSync } from "node:zlib";
import path from "node:path";
import { fileURLToPath } from "node:url";
import healpix from "@hscmap/healpix";

const here = path.dirname(fileURLToPath(import.meta.url));
const dataDir = path.join(here, "..", "public", "data");

const TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync";
const QUERY = `select hostname, tic_id, gaia_dr3_id, ra, dec, sy_dist, sy_dist_reflink, sy_pnum, st_teff, st_rad, sy_vmag
from pscomppars where sy_dist is not null`;

function decodeFootprint(fp) {
  const codes = new Uint8Array(12 * fp.nside * fp.nside);
  let i = 0;
  for (let k = 0; k < fp.rle.length; k += 2) {
    codes.fill(fp.rle[k], i, i + fp.rle[k + 1]);
    i += fp.rle[k + 1];
  }
  return codes;
}

// "<a refstr=STASSUN_ET_AL__2019 ...>TICv8</a>" -> "TICv8"
const refLabel = (html) =>
  (html ?? "").replace(/<[^>]+>/g, "").replace(/&amp;/g, "&").trim() || "unknown";

async function main() {
  const fp = JSON.parse(await readFile(path.join(dataDir, "rubin-footprint.json"), "utf8"));
  const codes = decodeFootprint(fp);
  const deg = Math.PI / 180;

  const url = `${TAP}?query=${encodeURIComponent(QUERY)}&format=json`;
  const res = await fetch(url);
  if (!res.ok) throw new Error(`Exoplanet Archive TAP ${res.status}`);
  const rows = await res.json();

  // pscomppars is one row per planet: collapse to one row per host.
  const hosts = new Map();
  for (const r of rows) {
    if (!hosts.has(r.hostname)) hosts.set(r.hostname, r);
  }

  const counts = { hosts: hosts.size, noTic: 0, outside: 0, kept: 0 };
  const refs = [];
  const cols = { name: [], tic: [], gaia: [], ra: [], dec: [], dist: [], npl: [], teff: [], rad: [], vmag: [], ref: [] };

  const sorted = [...hosts.values()].sort((a, b) => a.sy_dist - b.sy_dist);
  for (const r of sorted) {
    const tic = Number(String(r.tic_id ?? "").replace(/^TIC\s*/, ""));
    if (!tic) {
      counts.noTic++;
      continue;
    }
    const pix = healpix.ang2pix_nest(fp.nside, (90 - r.dec) * deg, r.ra * deg);
    if (codes[pix] === 0) {
      counts.outside++;
      continue;
    }
    const ref = refLabel(r.sy_dist_reflink);
    if (!refs.includes(ref)) refs.push(ref);

    cols.name.push(r.hostname);
    cols.tic.push(tic);
    cols.gaia.push(r.gaia_dr3_id ? String(r.gaia_dr3_id).replace(/^Gaia DR3\s*/, "") : "");
    cols.ra.push(Math.round(r.ra * 1e5) / 1e5);
    cols.dec.push(Math.round(r.dec * 1e5) / 1e5);
    cols.dist.push(Math.round(r.sy_dist * 100) / 100);
    cols.npl.push(r.sy_pnum ?? 1);
    cols.teff.push(r.st_teff ? Math.round(r.st_teff) : 0);
    // Stellar radius in solar radii and V magnitude as seen from Earth; 0 and 99 mean "not listed".
    cols.rad.push(r.st_rad ? Math.round(r.st_rad * 1000) / 1000 : 0);
    cols.vmag.push(r.sy_vmag != null ? Math.round(r.sy_vmag * 100) / 100 : 99);
    cols.ref.push(refs.indexOf(ref));
    counts.kept++;
  }

  const out = {
    source: "NASA Exoplanet Archive, Planetary Systems Composite Parameters (pscomppars)",
    source_url: "https://exoplanetarchive.ipac.caltech.edu/",
    distance_note:
      "sy_dist from the archive; mostly TICv8 (Stassun et al. 2019), i.e. Gaia DR2 parallax distances",
    footprint: fp.source_version,
    generated_at: new Date().toISOString().slice(0, 19) + "Z",
    count: counts.kept,
    dist_refs: refs,
    ...cols,
  };
  const json = JSON.stringify(out);
  await writeFile(path.join(dataDir, "hosts.json"), json);

  const tic = refs.indexOf("TICv8");
  const fromTic = tic < 0 ? 0 : cols.ref.filter((x) => x === tic).length;
  console.log(
    `hosts with distance: ${counts.hosts}, no TIC id: ${counts.noTic}, outside footprint: ${counts.outside}, kept: ${counts.kept}`,
  );
  console.log(`distance from TICv8 (Gaia DR2): ${fromTic}/${counts.kept}`);
  console.log(`hosts.json ${json.length} B raw, ${gzipSync(json).length} B gzip`);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

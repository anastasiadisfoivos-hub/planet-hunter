// Builds public/data/lab/star-lab.mock.json: the facts GET /stars/{tic}/lab will serve, for every
// planet host on the map, until the STARDATA session's endpoint is live. Run from web/:
//   node components/lab/data/build-star-lab.mjs [pscomppars.json]
// Real numbers: TESS magnitude, star mass and each known planet's period, orbit size, radius and mass,
// from the NASA Exoplanet Archive (Planetary Systems Composite Parameters). Pass a saved TAP JSON
// export to build offline; otherwise it is fetched.

import { readFileSync, writeFileSync } from "node:fs";

const TAP =
  "https://exoplanetarchive.ipac.caltech.edu/TAP/sync?format=json&query=" +
  encodeURIComponent("select pl_name,tic_id,pl_orbper,pl_orbsmax,pl_rade,pl_bmasse,st_mass,sy_tmag from pscomppars");

const rows = process.argv[2] ? JSON.parse(readFileSync(process.argv[2], "utf8")) : await (await fetch(TAP)).json();
const hosts = JSON.parse(readFileSync("public/data/hosts.json", "utf8"));
const want = new Set(hosts.tic);
const r = (v, d) => (v == null || !Number.isFinite(v) ? null : Number(v.toPrecision(d)));

const stars = {};
for (const x of rows) {
  const tic = Number(String(x.tic_id ?? "").replace(/^TIC\s*/, ""));
  if (!want.has(tic)) continue;
  const st = (stars[tic] ??= { mass: r(x.st_mass, 4), tmag: r(x.sy_tmag, 5), planets: [] });
  st.mass ??= r(x.st_mass, 4);
  st.tmag ??= r(x.sy_tmag, 5);
  // [name, period_d, a_au, radius (Earth radii), mass (Earth masses)]
  st.planets.push([x.pl_name, r(x.pl_orbper, 8), r(x.pl_orbsmax, 5), r(x.pl_rade, 4), r(x.pl_bmasse, 4)]);
}
for (const st of Object.values(stars)) st.planets.sort((a, b) => (a[1] ?? Infinity) - (b[1] ?? Infinity));

writeFileSync(
  "public/data/lab/star-lab.mock.json",
  JSON.stringify({
    meta: {
      demo: true,
      source: "NASA Exoplanet Archive, Planetary Systems Composite Parameters (pscomppars)",
      note: "Stand-in for GET /stars/{tic}/lab. Star mass, TESS magnitude and planets are real archive values; which stars have a light curve is a stand-in rule in lib/api.ts.",
      generated_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
      planet_fields: ["name", "period_d", "a_au", "radius_earth", "mass_earth"],
    },
    stars,
  }) + "\n",
);
console.log(`${Object.keys(stars).length} of ${want.size} hosts`);

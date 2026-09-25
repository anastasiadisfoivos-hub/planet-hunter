// Build web/public/data/land-110m.json: Earth's land outline as one SVG path in an equirectangular
// 360 x 180 box (x = longitude + 180, y = 90 - latitude), for the small Earth inset on Earth-frame
// events. Source: Natural Earth 1:110m land (public domain), via the world-atlas package.
//
//   node web/scripts/build-land.mjs

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createRequire } from "node:module";
import { feature } from "topojson-client";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(import.meta.url);
const topo = JSON.parse(await readFile(require.resolve("world-atlas/land-110m.json"), "utf8"));
const land = feature(topo, topo.objects.land);

const f = (n) => Math.round(n * 10) / 10;
let d = "";
for (const g of land.features) {
  const polys = g.geometry.type === "Polygon" ? [g.geometry.coordinates] : g.geometry.coordinates;
  for (const poly of polys) {
    for (const ring of poly) {
      // Split a ring where it crosses the antimeridian, so no line streaks across the map.
      let prev = null;
      ring.forEach(([lon, lat], i) => {
        const x = f(lon + 180);
        const y = f(90 - lat);
        const jump = prev && Math.abs(lon - prev) > 180;
        d += `${i === 0 || jump ? "M" : "L"}${x} ${y}`;
        prev = lon;
      });
      d += "Z";
    }
  }
}
const out = { source: "Natural Earth 1:110m land (public domain), via world-atlas", viewBox: "0 0 360 180", d };
await writeFile(path.join(here, "..", "public", "data", "land-110m.json"), JSON.stringify(out));
console.log(`land-110m.json ${JSON.stringify(out).length} B`);

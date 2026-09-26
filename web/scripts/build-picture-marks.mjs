// Where the event (or the target star) sits inside each survey or archive picture, as fractions of the frame,
// written to credits.json as `mark: { u, v }`. Pages draw a thin crosshair there (DESIGN.md, Pictures).
//
// hips2fits cutouts are gnomonic (TAN) projections centred on (ra, dec) with a field of view `fov` degrees across
// the width, north up and east left. The event is projected into that frame; for a cutout centred on the event
// itself this gives exactly the centre.
//
//   node scripts/build-picture-marks.mjs

import { readFileSync, writeFileSync } from "node:fs";

const root = new URL("../public/", import.meta.url);
const creditsPath = new URL("images/credits.json", root);
const credits = JSON.parse(readFileSync(creditsPath, "utf8"));
const { events } = JSON.parse(readFileSync(new URL("data/events.mock.json", root), "utf8"));
const byId = new Map(events.map((e) => [e.id, e]));
const r = Math.PI / 180;

function tan(ra0, dec0, ra, dec) {
  const [a0, d0, a, d] = [ra0 * r, dec0 * r, ra * r, dec * r];
  const cosc = Math.sin(d0) * Math.sin(d) + Math.cos(d0) * Math.cos(d) * Math.cos(a - a0);
  const x = (Math.cos(d) * Math.sin(a - a0)) / cosc / r;
  const y = (Math.cos(d0) * Math.sin(d) - Math.sin(d0) * Math.cos(d) * Math.cos(a - a0)) / cosc / r;
  return { x, y };
}

let n = 0;
for (const c of Object.values(credits)) {
  if (!c.archive) continue;
  const url = c.file || c.url;
  if (!url || !url.includes("hips2fits")) continue;
  const q = new URL(url).searchParams;
  const ra0 = Number(q.get("ra"));
  const dec0 = Number(q.get("dec"));
  const fov = Number(q.get("fov"));
  const w = Number(q.get("width"));
  const h = Number(q.get("height")) || w;
  const e = c.event ? byId.get(c.event) : null;
  const ra = e?.location?.ra_deg ?? c.ra ?? ra0;
  const dec = e?.location?.dec_deg ?? c.dec ?? dec0;
  const { x, y } = tan(ra0, dec0, ra, dec);
  const u = 0.5 - x / fov;
  const v = 0.5 - (y / fov) * (w / h);
  if (u < 0 || u > 1 || v < 0 || v > 1) continue;
  c.mark = { u: Math.round(u * 1e4) / 1e4, v: Math.round(v * 1e4) / 1e4 };
  n++;
}

writeFileSync(creditsPath, JSON.stringify(credits, null, 1) + "\n");
console.log(`${n} pictures marked`);

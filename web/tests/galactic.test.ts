import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import {
  constellationBox,
  constellationLabels,
  constellationOf,
  constellationPath,
  panoUV,
  panoXY,
  raDecToGalactic,
  windowAround,
  type BoundsData,
  type LinesData,
  type NamesData,
} from "../lib/galactic.ts";

const load = <T>(f: string) => JSON.parse(readFileSync(new URL(`../public/data/sky/${f}`, import.meta.url), "utf8")) as T;
const lines = load<LinesData>("constellation-lines.json");
const names = load<NamesData>("constellation-names.json");
const bounds = load<BoundsData>("constellation-bounds.json");
const W = 6000;
const H = 3000;

const close = (a: number, b: number, tol: number, msg?: string) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ""} ${a} vs ${b}`);

/** An independent galactic conversion (spherical trigonometry), to check the matrix in lib/sky.ts. */
function galacticByFormula(ra: number, dec: number) {
  const r = Math.PI / 180;
  const [a, d, raG, decG, lN] = [ra * r, dec * r, 192.85948 * r, 27.12825 * r, 122.93192 * r];
  const b = Math.asin(Math.sin(d) * Math.sin(decG) + Math.cos(d) * Math.cos(decG) * Math.cos(a - raG));
  const l = lN - Math.atan2(Math.cos(d) * Math.sin(a - raG), Math.sin(d) * Math.cos(decG) - Math.cos(d) * Math.sin(decG) * Math.cos(a - raG));
  return { l: (((l / r) % 360) + 360) % 360, b: b / r };
}

test("RA/Dec to galactic agrees with an independent formula", () => {
  for (const [ra, dec] of [[0, 0], [83.82, -5.39], [266.42, -29], [10.68, 41.27], [150, 70], [300, -60], [88.79, 7.41]]) {
    const g = raDecToGalactic(ra, dec);
    const f = galacticByFormula(ra, dec);
    close(((g.l - f.l + 540) % 360) - 180, 0, 1e-3, `l at ${ra},${dec}`);
    close(g.b, f.b, 1e-3, `b at ${ra},${dec}`);
  }
});

test("Sgr A* lands at the panorama centre", () => {
  const { u, v } = panoUV(266.41683, -29.00781);
  close(u, 0.5, 0.001, "u");
  close(v, 0.5, 0.001, "v");
});

test("the north galactic pole is the top edge; longitude increases to the left", () => {
  close(panoUV(192.85948, 27.12825).v, 0, 1e-5, "NGP");
  // l = 90 (towards Cygnus) is left of centre, l = 270 right of it.
  const cyg = raDecToGalactic(318, 48);
  assert.ok(cyg.l > 80 && cyg.l < 100, `Cygnus l ${cyg.l}`);
  assert.ok(panoUV(318, 48).u < 0.5);
});

test("Betelgeuse lands inside Orion's lines", () => {
  const p = panoXY(88.7929, 7.4071, W, H);
  const box = constellationBox(lines, "Ori", W, H)!;
  assert.ok(p.x > box.x0 && p.x < box.x1 && p.y > box.y0 && p.y < box.y1, `Betelgeuse ${JSON.stringify(p)} in ${JSON.stringify(box)}`);
  assert.equal(constellationOf(88.7929, 7.4071, bounds, names), "Orion");
});

test("M31 lands inside Andromeda's lines", () => {
  const p = panoXY(10.6847, 41.269, W, H);
  const box = constellationBox(lines, "And", W, H)!;
  assert.ok(p.x > box.x0 && p.x < box.x1 && p.y > box.y0 && p.y < box.y1, `M31 ${JSON.stringify(p)} in ${JSON.stringify(box)}`);
  assert.equal(constellationOf(10.6847, 41.269, bounds, names), "Andromeda");
});

test("constellationOf across the sky, including the RA seam and the poles", () => {
  const cases: [number, number, string][] = [
    [73.08, 5.15, "Orion"],
    [266.42, -29, "Sagittarius"],
    [250, -5, "Ophiuchus"],
    [153.5, 36.9, "Leo Minor"],
    [0.5, 0.5, "Pisces"],
    [2.0969, 29.0904, "Andromeda"], // Alpheratz, just east of the RA seam
    [359.8, 60, "Cassiopeia"], // just west of it
    [37.95, 89.26, "Ursa Minor"],
    [95, -89, "Octans"],
  ];
  for (const [ra, dec, name] of cases) assert.equal(constellationOf(ra, dec, bounds, names), name, `${ra}, ${dec}`);
});

test("a window around an event keeps it centred, and the overlay has no seam-crossing strokes", () => {
  const win = windowAround(73.08, 5.15, 56, 34, W, H);
  const p = panoXY(73.08, 5.15, W, H);
  close(p.x - win.x0, win.w / 2, 1e-6);
  const d = constellationPath(lines, win);
  assert.ok(d.length > 0);
  for (const seg of d.split("M").slice(1)) {
    const [a, b] = seg.split("L").map((xy) => xy.split(" ").map(Number));
    assert.ok(Math.abs(b[0] - a[0]) < win.w, `segment too long: ${seg}`);
  }
  assert.ok(constellationLabels(names, win).some((l) => l.name === "Orion"));
});

test("a window that straddles l = 180 (Taurus/Auriga) still draws its lines", () => {
  const win = windowAround(84, 26, 56, 34, W, H); // near the galactic anticentre
  assert.ok(constellationPath(lines, win).length > 200);
});

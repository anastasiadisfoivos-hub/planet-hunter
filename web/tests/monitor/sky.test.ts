import { test } from "node:test";
import assert from "node:assert/strict";
import { eclipticToEquatorial, galacticToEquatorial, mollweide, skyPath } from "../../components/monitor/sky.ts";
import { starHex } from "../../components/monitor/starColour.ts";

const near = (a: number, b: number, tol: number, what: string) => assert.ok(Math.abs(a - b) < tol, `${what}: ${a} vs ${b}`);

test("sky frames: the galactic centre and pole, and the ecliptic, land where they should", () => {
  const [ra, dec] = galacticToEquatorial(0, 0);
  near(ra, 266.405, 0.05, "galactic centre RA");
  near(dec, -28.936, 0.05, "galactic centre Dec");
  const [, pdec] = galacticToEquatorial(0, 90);
  near(pdec, 27.128, 0.05, "north galactic pole Dec");
  const [era, edec] = eclipticToEquatorial(90, 0);
  near(era, 90, 0.01, "solstice RA");
  near(edec, 23.439, 0.01, "solstice Dec");
});

test("Mollweide: RA 0h at the centre, RA grows to the left, poles at the top and bottom", () => {
  assert.deepEqual(mollweide(0, 0).map((v) => +v.toFixed(6)), [0, 0]);
  assert.ok(mollweide(90, 0)[0] < 0, "6h is left of centre");
  assert.ok(mollweide(270, 0)[0] > 0, "18h is right of centre");
  near(mollweide(0, 90)[1], 1, 1e-6, "north pole");
  near(mollweide(179.9, 0)[0], -2, 0.01, "12h at the left edge");
  assert.equal((skyPath([[170, 0], [190, 0]], 400).match(/M/g) ?? []).length, 2, "the pen lifts across the seam");
});

test("star colour: cool stars orange-red, the Sun near white, hot stars blue-white", () => {
  const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [r3, , b3] = rgb(starHex(3000)!);
  assert.ok(r3 > 240 && b3 < 90, "3000 K is orange-red");
  const [r10, , b10] = rgb(starHex(10000)!);
  assert.ok(b10 > r10, "10000 K is bluer than red");
  assert.equal(starHex(null), null);
});

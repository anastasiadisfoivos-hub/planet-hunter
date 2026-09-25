import { test } from "node:test";
import assert from "node:assert/strict";
import { bvToTeff, DISPLAY_SATURATION, starColor, teffToSrgb } from "../lib/starColor.ts";

const hex = (c: readonly number[]) => c.map((v) => Math.round(v * 255).toString(16).padStart(2, "0")).join("");

test("teffToSrgb reads Charity's table at its rows", () => {
  assert.equal(hex(teffToSrgb(1000)), "ff3800");
  assert.equal(hex(teffToSrgb(6600)), "fef9ff");
  assert.equal(hex(teffToSrgb(40000)), "9bbcff");
});

test("teffToSrgb interpolates and clamps", () => {
  const mid = teffToSrgb(1050);
  assert.ok(mid[1] > teffToSrgb(1000)[1] && mid[1] < teffToSrgb(1100)[1]);
  assert.deepEqual(teffToSrgb(500), teffToSrgb(1000));
  assert.deepEqual(teffToSrgb(57000), teffToSrgb(40000));
});

test("bvToTeff (Ballesteros 2012) gives the Sun and Vega roughly right", () => {
  assert.ok(Math.abs(bvToTeff(0.65) - 5780) < 150);
  assert.ok(Math.abs(bvToTeff(0.0) - 9800) < 600);
  assert.ok(bvToTeff(1.5) < 4000);
});

test("starColor boosts saturation but keeps the peak channel at 1", () => {
  const raw = teffToSrgb(3200);
  const boosted = starColor(3200);
  assert.equal(Math.max(...boosted), 1);
  const spread = (c: readonly number[]) => Math.max(...c) - Math.min(...c);
  assert.ok(spread(boosted) > spread(raw));
  assert.ok(DISPLAY_SATURATION > 1);
});

test("missing temperature is neutral white with no boost", () => {
  assert.deepEqual(starColor(0), [1, 1, 1]);
  assert.deepEqual(starColor(Number.NaN), [1, 1, 1]);
});

test("red dwarfs read red, hot stars read blue", () => {
  const m = starColor(3000);
  const b = starColor(20000);
  assert.ok(m[0] > m[2]);
  assert.ok(b[2] > b[0]);
});

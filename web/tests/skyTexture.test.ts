import { test } from "node:test";
import assert from "node:assert/strict";
import { bakeFootprintField, bakeHeatmapField, texelAt, texelPixels } from "../lib/skyTexture.ts";

test("heatmap uses RING ordering: RING pixel 0 is at the north pole", () => {
  // In RING ordering pixel 0 is the first pixel of the northernmost ring; in NESTED it is on the equator.
  const { field } = bakeHeatmapField({ generated_at: "", grid: "healpix nside=32", cells: [{ pix: 0, counts: { supernova: 5 } }] });
  assert.ok(field[texelAt(50, 89.5)] > 0.9, "lit near the north pole");
  assert.equal(field[texelAt(50, 0)], 0, "dark on the equator");
});

test("RING and NESTED tables differ, and each is computed once", () => {
  const ring = texelPixels(32, "ring");
  assert.equal(texelPixels(32, "ring"), ring, "cached");
  const nest = texelPixels(32, "nest");
  assert.notDeepEqual(ring.slice(0, 2000), nest.slice(0, 2000));
});

test("the lookups never call console.assert", () => {
  const orig = console.assert;
  let calls = 0;
  console.assert = () => void calls++;
  try {
    texelPixels(8, "ring");
  } finally {
    console.assert = orig;
  }
  assert.equal(calls, 0);
});

test("coverage field is blurred: a smooth ramp across the footprint edge", () => {
  // nside 1, NESTED: pixels 0 to 3 are the four northern base pixels (pole down to the equator, roughly).
  const codes = new Uint8Array(12);
  codes.fill(1, 0, 4);
  const f = bakeFootprintField(1, codes);
  assert.ok(f[texelAt(40, 80)] > 0.99 && f[texelAt(40, -60)] < 0.01);
  // Walk south along RA 40: the field must pass through several intermediate values, not jump 1 -> 0.
  const steps: number[] = [];
  for (let d = 60; d >= -40; d -= 0.1) steps.push(f[texelAt(40, d)]);
  const between = steps.filter((v) => v > 0.05 && v < 0.95).length;
  assert.ok(between >= 3, `samples on the ramp: ${between}`);
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

test("the stored demo result is the pipeline's real WASP-18 run", () => {
  const r = JSON.parse(readFileSync(new URL("../public/data/analysis/wasp-18/result.json", import.meta.url), "utf8"));
  assert.equal(r.target.tic_id, 100100827);
  assert.equal(r.discoveries[0].name_if_known, "WASP-18 b");
  assert.deepEqual(Object.keys(r.timings_s).filter((k) => k !== "total"), ["resolve", "fetch", "search", "vet_known_flares"]);
  for (const p of r.plots) readFileSync(new URL(`../public/data/analysis/wasp-18/${p}`, import.meta.url));
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import type { Sensitivity } from "../../lib/api.ts";
import { toSensitivity, type HuntSensitivity } from "../../components/finder/sensitivityData.ts";

test("hunt's fast-search sensitivity file (26 Sep) maps to the same grid the mock was built with", () => {
  const hunt = JSON.parse(readFileSync(new URL("../../../hunt/results/sensitivity_hunt_2026-09-26.json", import.meta.url), "utf8")) as HuntSensitivity;
  const mock = JSON.parse(readFileSync(new URL("../../public/data/monitor/sensitivity.json", import.meta.url), "utf8")) as Sensitivity;
  const live = toSensitivity(hunt);
  assert.deepEqual(live.recovery_pct, mock.recovery_pct);
  assert.deepEqual(live.n_injected, mock.n_injected);
  assert.equal(live.stars_used, mock.stars_used);
  assert.equal(live.overall_recovery_pct, mock.overall_recovery_pct);
  assert.equal(toSensitivity(mock), mock, "the page's own shape passes through");
});

test("the deep search's sensitivity file keeps the same main grid shape", () => {
  const deep = JSON.parse(readFileSync(new URL("../../../hunt/results/sensitivity.json", import.meta.url), "utf8")) as HuntSensitivity;
  const s = toSensitivity(deep);
  assert.equal(s.recovery_pct.length, s.radius_edges_rearth.length - 1);
  assert.ok(s.recovery_pct.every((row) => row.length === s.period_edges_d.length - 1));
  assert.equal(s.stars_used, deep.n_stars);
});

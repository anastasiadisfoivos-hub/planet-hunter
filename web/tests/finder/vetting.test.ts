import { test } from "node:test";
import assert from "node:assert/strict";
import { gaiaVariable, mimics, notRun, ran } from "../../components/finder/vetting.ts";
import type { Vetting } from "../../lib/api.ts";

const gaia = (over: Partial<Vetting["gaia"]>): Vetting["gaia"] => ({ ruwe: 1, neighbours: [], binary_hint: false, ...over });

test("neighbours that could fake the dip: skyvet's count and radius, or the mock's flags", () => {
  const skyvet = gaia({
    radius_arcsec: 63,
    n_could_mimic: 2,
    neighbours: [{ source_id: "1", sep_arcsec: 5, gmag: 12, could_mimic: true, required_depth: 0.2 }],
  });
  assert.deepEqual(mimics(skyvet), { count: 2, radius: 63 }, "the count covers neighbours not listed");
  const mock = gaia({ neighbours: [{ gaia_id: "1", sep_arcsec: 5, gmag: 12, can_mimic: true }, { gaia_id: "2", sep_arcsec: 9, gmag: 18, can_mimic: false }] });
  assert.deepEqual(mimics(mock), { count: 1, radius: 42 });
});

test("Gaia variability: skyvet's object is variable only when flagged VARIABLE", () => {
  assert.equal(gaiaVariable({ phot_variable_flag: "VARIABLE", class: "EP" }), true);
  assert.equal(gaiaVariable({ phot_variable_flag: "NOT_AVAILABLE" }), false);
  assert.equal(gaiaVariable(true), true);
  assert.equal(gaiaVariable(null), false);
});

test("a part that did not run says so, with its reason", () => {
  assert.equal(ran({ ran: false }), false);
  assert.equal(ran({}), true, "the mock's blocks have no ran flag");
  assert.equal(notRun({ reason: "single dip: no period" }), "not run: single dip: no period");
  assert.equal(notRun({}), "not run yet");
});

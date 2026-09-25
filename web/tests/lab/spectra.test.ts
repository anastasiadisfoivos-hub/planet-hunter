import { test } from "node:test";
import assert from "node:assert/strict";
import { formatTimesSun, planetSlug, telluricSpecies } from "../../components/lab/spectra.ts";

test("Earth's air: oxygen A and B bands and water are telluric, solar lines are not", () => {
  assert.equal(telluricSpecies({ nm: 759.4, element: "O2", label: "A" }), "O2");
  assert.equal(telluricSpecies({ nm: 686.7, element: "O", label: "B" }), "O2");
  assert.equal(telluricSpecies({ nm: 686.7, element: "O₂", label: "" }), "O2");
  assert.equal(telluricSpecies({ nm: 822.7, element: "H2O", label: "" }), "H2O");
  assert.equal(telluricSpecies({ nm: 720, element: "", label: "telluric water" }), "H2O");
  assert.equal(telluricSpecies({ nm: 589.0, element: "Na", label: "D2" }), null);
  assert.equal(telluricSpecies({ nm: 656.28, element: "H", label: "C (H-alpha)" }), null);
  assert.equal(telluricSpecies({ nm: 777.2, element: "O", label: "O I triplet" }), null);
  assert.equal(telluricSpecies({ nm: 630.03, element: "O", label: "[O I]" }), null);
});

test("planet slugs and abundance ratios", () => {
  assert.equal(planetSlug("WASP-121 b"), "wasp-121-b");
  assert.equal(planetSlug("HD 209458 b"), "hd-209458-b");
  assert.equal(formatTimesSun(0.3), "2.0×");
  assert.equal(formatTimesSun(-0.3), "0.50×");
});

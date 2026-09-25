import { test } from "node:test";
import assert from "node:assert/strict";
import {
  aOverR,
  coveredFraction,
  grazingInclination,
  impactParameter,
  keplerAu,
  kFromDepth,
  massFromTeff,
  modelDepth,
  planetRadius,
  rmsPpm,
  transitFlux,
} from "../../components/lab/transit.ts";

const near = (a: number, b: number, tol: number, msg?: string) => assert.ok(Math.abs(a - b) <= tol, msg ?? `${a} vs ${b}`);

test("Kepler: Earth's year around the Sun is 1 AU; Jupiter's 11.86 years is 5.2 AU", () => {
  near(keplerAu(1, 365.25), 1, 1e-12);
  near(keplerAu(1, 11.862 * 365.25), 5.2, 0.01);
  // A four times heavier star pulls the same year's orbit out by ∛4.
  near(keplerAu(4, 365.25), Math.cbrt(4), 1e-12);
});

test("Kepler: WASP-121 b and WASP-18 b land within 2.5% of the NASA archive's orbit sizes", () => {
  // The archive's composite table takes mass and orbit size from different papers, so they agree
  // only to a couple of percent. Archive: WASP-121 M = 1.33 Suns, P = 1.27492504 d, a = 0.02571 AU.
  near(keplerAu(1.33, 1.27492504) / 0.02571, 1, 0.025);
  // Archive: WASP-18 M = 1.294 Suns, P = 0.94145223 d, a = 0.02024 AU.
  near(keplerAu(1.294, 0.94145223) / 0.02024, 1, 0.025);
});

test("a/R★: 1 AU around the Sun is about 215 solar radii", () => {
  near(aOverR(1, 1), 215.03, 0.01);
});

test("Transit depth: a central transit blocks k² of a uniform star", () => {
  for (const k of [0.01, 0.1, 0.125, 0.2]) {
    near(modelDepth({ k, aR: 3.8, inclinationDeg: 90 }), k * k, 1e-12, `k = ${k}`);
  }
  // WASP-121 b's pipeline depth, 1.579%, means Rp/R★ of about 0.1257.
  near(kFromDepth(0.01578852), 0.12565, 0.0001);
});

test("Transit depth: grazing is shallower, a miss is nothing, and out of transit is 1", () => {
  const k = 0.12;
  const aR = 4;
  const deep = modelDepth({ k, aR, inclinationDeg: 90 });
  const graze = grazingInclination(aR, k);
  const partial = modelDepth({ k, aR, inclinationDeg: graze + 1.5 });
  assert.ok(partial > 0 && partial < deep, `partial ${partial} vs central ${deep}`);
  near(impactParameter(aR, graze), 1 + k, 1e-9);
  assert.equal(modelDepth({ k, aR, inclinationDeg: graze - 0.5 }), 0);
  assert.equal(transitFlux(0.25, { k, aR, inclinationDeg: 90 }), 1);
  assert.equal(transitFlux(0.5, { k, aR, inclinationDeg: 90 }), 1); // behind the star: no dip
});

test("Covered fraction is continuous at the edges and symmetric in time", () => {
  const k = 0.1;
  near(coveredFraction(1 - k, k), k * k, 1e-12);
  near(coveredFraction(1 - k + 1e-9, k), k * k, 1e-6);
  near(coveredFraction(1 + k - 1e-9, k), 0, 1e-6);
  const m = { k, aR: 5, inclinationDeg: 88 };
  near(transitFlux(0.01, m), transitFlux(-0.01, m), 1e-15);
});

test("Fit score: the true model fits its own curve exactly", () => {
  const m = { k: 0.1, aR: 5, inclinationDeg: 89 };
  const phase = Array.from({ length: 101 }, (_, i) => (i - 50) / 1000);
  const flux = phase.map((p) => transitFlux(p, m));
  near(rmsPpm(phase, flux, m), 0, 1e-9);
  assert.ok(rmsPpm(phase, flux, { ...m, k: 0.12 }) > 100);
});

test("Planet radius: Rp/R★ 0.1 of the Sun is about 10.9 Earths, 0.97 Jupiters", () => {
  const r = planetRadius(0.1, 1);
  near(r.earth, 10.91, 0.01);
  near(r.jupiter, 0.973, 0.001);
});

test("Mass from temperature: the Sun is 1, cooler is lighter", () => {
  near(massFromTeff(5772), 1, 1e-12);
  assert.ok(massFromTeff(3200) < massFromTeff(5000));
  assert.ok(massFromTeff(9000) > 1.5);
});

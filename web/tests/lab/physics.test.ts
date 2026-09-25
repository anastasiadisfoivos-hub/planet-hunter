import { test } from "node:test";
import assert from "node:assert/strict";
import {
  apparentMag,
  blackbodyCurve,
  blueRedRatio,
  distanceMpc,
  fitH0,
  foldAndBin,
  h0FromPoint,
  hubbleTimeGyr,
  phaseOf,
  pitchFor,
  planck,
  rmsResidual,
  speedKms,
  temperatureColor,
  wavelengthRgb,
  wienPeakNm,
} from "../../components/lab/physics.ts";

test("Wien peak: the Sun near 502 nm, 3000 K in the infrared, 30000 K in the ultraviolet", () => {
  assert.ok(Math.abs(wienPeakNm(5772) - 502.0) < 0.5);
  assert.ok(Math.abs(wienPeakNm(3000) - 965.9) < 0.5);
  assert.ok(wienPeakNm(30000) < 100);
  // Twice as hot, peak at half the wavelength.
  assert.ok(Math.abs(wienPeakNm(4000) / wienPeakNm(8000) - 2) < 1e-12);
});

test("Wien peak matches the maximum of the Planck curve", () => {
  for (const t of [2000, 5772, 12000, 40000]) {
    const peak = wienPeakNm(t);
    const c = blackbodyCurve(t, peak * 0.5, peak * 1.5, 2001);
    const at = c.nm[c.value.indexOf(Math.max(...c.value))];
    assert.ok(Math.abs(at - peak) / peak < 0.002, `${t} K: curve peaks at ${at}, Wien says ${peak}`);
  }
});

test("Planck: hotter is brighter at every wavelength", () => {
  for (const nm of [200, 500, 1000, 2000]) assert.ok(planck(nm, 10000) > planck(nm, 5000));
  assert.equal(planck(10, 2000), 0);
});

test("blackbody colour: cool stars red, the Sun near white, hot stars blue", () => {
  const cool = temperatureColor(3000);
  assert.equal(cool[0], 1);
  assert.ok(cool[2] < 0.5, "3000 K has little blue");
  const hot = temperatureColor(30000);
  assert.equal(hot[2], 1);
  assert.ok(hot[0] < hot[2]);
  const sun = temperatureColor(5772);
  assert.ok(Math.min(...sun) > 0.8, "the Sun is close to white");
  assert.ok(blueRedRatio(3000) < 1 && blueRedRatio(20000) > 1);
});

test("visible colour of a wavelength", () => {
  const red = wavelengthRgb(650);
  assert.ok(red[0] > 0.9 && red[2] === 0);
  const blue = wavelengthRgb(460);
  assert.ok(blue[2] > 0.9 && blue[0] === 0);
  assert.deepEqual(wavelengthRgb(300), [0, 0, 0]);
  assert.deepEqual(wavelengthRgb(900), [0, 0, 0]);
});

test("H0 fit recovers the slope of exact Hubble-law data", () => {
  const pts = [10, 40, 90, 150, 300, 420].map((d) => ({ d, v: 70 * d }));
  assert.ok(Math.abs(fitH0(pts) - 70) < 1e-9);
  assert.equal(rmsResidual(pts, 70), 0);
  assert.ok(Number.isNaN(fitH0([])));
});

test("H0 from supernova brightness and redshift, end to end", () => {
  // A candle at z = 0.02 in a 70 km/s/Mpc universe.
  const d = speedKms(0.02) / 70;
  const m = apparentMag(d);
  assert.ok(Math.abs(distanceMpc(m) - d) < 1e-9);
  assert.ok(Math.abs(h0FromPoint(distanceMpc(m), speedKms(0.02)) - 70) < 1e-9);
  // Scattered data still lands close.
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647 - 0.5) * 0.3;
  const pts = [0.012, 0.02, 0.03, 0.045, 0.06, 0.08, 0.1].map((z) => ({ d: distanceMpc(apparentMag(speedKms(z) / 70) + rnd()), v: speedKms(z) }));
  assert.ok(Math.abs(fitH0(pts) - 70) < 7);
  assert.ok(Math.abs(hubbleTimeGyr(70) - 13.97) < 0.01);
});

test("folding puts the transit at phase 0", () => {
  assert.equal(phaseOf(10, 2, 10), 0);
  assert.ok(Math.abs(phaseOf(11, 2, 10) + 0.5) < 1e-12);
  const time = Array.from({ length: 400 }, (_, i) => i * 0.05);
  const flux = time.map((t) => (Math.abs(phaseOf(t, 1.3, 0.4)) < 0.03 ? 0.99 : 1));
  const f = foldAndBin(time, flux, 1.3, 0.4, 50);
  const min = f.phase[f.flux.indexOf(Math.min(...f.flux))];
  assert.ok(Math.abs(min) < 0.03);
});

test("pitch falls with brightness", () => {
  assert.equal(pitchFor(1, 0.98, 1), 784);
  assert.equal(pitchFor(0.98, 0.98, 1), 196);
  assert.ok(pitchFor(0.99, 0.98, 1) < pitchFor(0.995, 0.98, 1));
});

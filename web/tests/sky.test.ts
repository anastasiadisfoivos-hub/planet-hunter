import { test } from "node:test";
import assert from "node:assert/strict";
import { galactic, radecToVec, separationDeg, vecToRadec } from "../lib/sky.ts";
import { julianDate, sunRaDec } from "../lib/sun.ts";

const close = (a: number, b: number, tol: number, msg?: string) => assert.ok(Math.abs(a - b) <= tol, `${msg ?? ""} ${a} vs ${b}`);

test("radecToVec and vecToRadec round-trip", () => {
  for (const [ra, dec] of [[0, 0], [83.82, -5.39], [266.42, -29], [359.9, 89.5], [180, -89.9], [12.5, 45]]) {
    const back = vecToRadec(radecToVec(ra, dec));
    close(back.dec, dec, 1e-9, "dec");
    close(((back.ra - ra + 540) % 360) - 180, 0, 1e-9, "ra");
  }
});

test("scene axes: +y north pole, +x RA 0h, -z RA 6h", () => {
  const n = radecToVec(0, 90);
  close(n[1], 1, 1e-12);
  const [x, , z] = radecToVec(90, 0);
  close(x, 0, 1e-12);
  close(z, -1, 1e-12);
});

test("separation is accurate at tiny and large angles", () => {
  close(separationDeg(radecToVec(10, 10), radecToVec(10, 10.0001)), 0.0001, 1e-10);
  close(separationDeg(radecToVec(0, 0), radecToVec(180, 0)), 180, 1e-9);
  close(separationDeg(radecToVec(0, 0), radecToVec(90, 0)), 90, 1e-9);
});

test("galactic centre and north galactic pole", () => {
  const gc = galactic(266.405, -28.936);
  close(gc.b, 0, 0.05, "b");
  close(((gc.l + 180) % 360) - 180, 0, 0.05, "l");
  close(galactic(192.8595, 27.1283).b, 90, 0.01, "NGP");
});

test("Julian date at the J2000 epoch", () => {
  close(julianDate(Date.parse("2000-01-01T12:00:00Z")), 2451545.0, 1e-9);
});

test("the Sun: J2000 epoch, 2026 equinox and solstice", () => {
  // Astronomical Almanac: 2000-01-01 12:00 TT, RA 18h 45m 09s (281.29 deg), Dec -23.03.
  const j2000 = sunRaDec(Date.parse("2000-01-01T12:00:00Z"));
  close(j2000.ra, 281.29, 0.05, "ra");
  close(j2000.dec, -23.03, 0.03, "dec");
  // March equinox 2026-03-20 14:46 UTC: RA 0, Dec 0.
  const eq = sunRaDec(Date.parse("2026-03-20T14:46:00Z"));
  close(Math.min(eq.ra, 360 - eq.ra), 0, 0.05, "equinox ra");
  close(eq.dec, 0, 0.02, "equinox dec");
  // June solstice 2026-06-21 08:24 UTC: RA 90, Dec +23.44.
  const sol = sunRaDec(Date.parse("2026-06-21T08:24:00Z"));
  close(sol.ra, 90, 0.05, "solstice ra");
  close(sol.dec, 23.44, 0.02, "solstice dec");
});

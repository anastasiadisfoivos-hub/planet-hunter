import { test } from "node:test";
import assert from "node:assert/strict";
import { buildMarkers, SUN_FAN_DEG } from "../lib/markers.ts";
import { radecToVec, separationDeg } from "../lib/sky.ts";
import type { SkyEvent } from "../lib/contract.ts";

const NOW = Date.parse("2026-09-25T16:03:00Z");
const base: Omit<SkyEvent, "id" | "type" | "location"> = {
  title: "t", summary: "", source: "donki", source_url: "https://x", observed_at: "2026-09-24T00:00:00Z",
  reported_at: "2026-09-24T00:00:00Z", confidence: 1, confidence_basis: "official_report", brightness_mag: null, images: [], raw: {},
};

test("sky events at their position, Earth events not on the map", () => {
  const { markers } = buildMarkers(
    [
      { ...base, id: "a", type: "supernova", location: { frame: "sky", ra_deg: 83.8, dec_deg: -5.4, error_deg: 0 } },
      { ...base, id: "b", type: "fireball", location: { frame: "earth", lat_deg: 10, lon_deg: 20, alt_km: 30 } },
    ],
    NOW,
  );
  assert.deepEqual(markers.map((m) => m.id), ["a"]);
  assert.equal(markers[0].ra, 83.8);
  assert.equal(markers[0].category, "transients");
});

test("Sun events sit on the Sun's current position, fanned out within 1.2 degrees", () => {
  const events: SkyEvent[] = [0, 1, 2, 3].map((i) => ({ ...base, id: `s${i}`, type: "coronal_mass_ejection", location: { frame: "sun" } }));
  const { markers, sun } = buildMarkers(events, NOW);
  // Late September: the Sun is just past the autumn equinox (RA about 182, Dec about -1).
  assert.ok(Math.abs(sun.ra - 182) < 1.5 && Math.abs(sun.dec + 1) < 1, `${sun.ra} ${sun.dec}`);
  for (const m of markers) {
    const sep = separationDeg(radecToVec(m.ra, m.dec), radecToVec(sun.ra, sun.dec));
    assert.ok(Math.abs(sep - SUN_FAN_DEG) < 0.01, `sep ${sep}`);
    assert.ok(m.onSun);
  }
  const single = buildMarkers([events[0]], NOW);
  assert.ok(separationDeg(radecToVec(single.markers[0].ra, single.markers[0].dec), radecToVec(sun.ra, sun.dec)) < 1e-9);
});

test("fresh (pulsing) means observed in the last 24 hours", () => {
  const mk = (observed_at: string) =>
    buildMarkers([{ ...base, id: observed_at, type: "supernova", observed_at, location: { frame: "sky", ra_deg: 1, dec_deg: 1, error_deg: 0 } }], NOW).markers[0];
  assert.equal(mk("2026-09-25T10:00:00Z").fresh, true);
  assert.equal(mk("2026-09-24T15:00:00Z").fresh, false);
});

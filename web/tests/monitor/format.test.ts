import { test } from "node:test";
import assert from "node:assert/strict";
import {
  detectionLabel,
  fmtDepth,
  fmtPeriod,
  fmtSpan,
  modeLabel,
  modeShort,
  observedLine,
  starKind,
} from "../../components/monitor/format.ts";

test("mode is said plainly: Live, or Replay of the day's search", () => {
  assert.equal(modeLabel("live", null), "Live");
  assert.equal(modeLabel("replay", "2026-09-26T07:57:39Z"), "Replay of the 26 Sep 2026 search");
  assert.equal(modeLabel("replay", null), "Replay");
  assert.equal(modeShort("live"), "LIVE");
  assert.equal(modeShort("replay"), "REPLAY");
});

test("data dates: observed … by TESS, in the brief's form", () => {
  assert.equal(fmtSpan("2026-08-02T01:00:00Z", "2026-08-28T20:00:00Z"), "2 to 28 Aug 2026");
  assert.equal(fmtSpan("2024-08-10T21:36:31Z", "2024-09-05T18:00:18Z"), "10 Aug to 5 Sep 2024");
  assert.equal(fmtSpan("2025-12-30T00:00:00Z", "2026-01-24T00:00:00Z"), "30 Dec 2025 to 24 Jan 2026");
  assert.equal(fmtSpan("2023-07-01T03:32:45Z", "2026-06-13T01:08:56Z"), "Jul 2023 to Jun 2026");
  assert.equal(observedLine("2026-08-02T01:00:00Z", "2026-08-28T20:00:00Z", [109]), "observed 2 to 28 Aug 2026 by TESS");
  assert.equal(observedLine("2023-07-01T03:32:45Z", "2026-06-13T01:08:56Z", [67, 94, 104]), "observed Jul 2023 to Jun 2026 by TESS, 3 sectors");
  assert.equal(observedLine(null, null, [67]), "TESS sector 67");
});

test("units: ppm under 1000, % above; hours under a day", () => {
  assert.equal(fmtDepth(840), "840 ppm");
  assert.equal(fmtDepth(7864.9), "0.79%");
  assert.equal(fmtDepth(null), "depth not measured");
  assert.equal(fmtPeriod(0.717098), "17.2 h");
  assert.equal(fmtPeriod(2.336961), "2.34 d");
  assert.equal(detectionLabel({ t0: 0, duration_h: 1, depth_ppm: 5092.8, period_d: 2.336961, kind: "periodic", outcome: "known", reason: "" }), "every 2.34 d · 0.51%");
  assert.equal(detectionLabel({ t0: 0, duration_h: 1, depth_ppm: 300, period_d: null, kind: "single", outcome: "rejected", reason: "" }), "one dip · 300 ppm");
});

test("a kind of star in words, from the TIC", () => {
  assert.equal(starKind(4439, 0.76), "a K dwarf");
  assert.equal(starKind(3027, 0.3), "an M dwarf");
  assert.equal(starKind(6030, 1.6), "an F dwarf");
  assert.equal(starKind(6226, 1.9), "an F subgiant");
  assert.equal(starKind(4800, 11), "a red giant");
  assert.equal(starKind(null, null), "a star");
});

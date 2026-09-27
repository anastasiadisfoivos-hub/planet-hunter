import { test } from "node:test";
import assert from "node:assert/strict";
import { BREAK_TAPE_D, buildTape, dipTimes, drawSeconds, easeInOut, fluxRange, lowerBound, marksReached, penAt, phaseAt, RAMP_S, DAYS_PER_SECOND, HOLD_S, ADVANCE_S } from "../../components/monitor/trace.ts";
import type { Detection } from "../../lib/api.ts";

/** Two sectors a year apart, each 10 days at 10-minute cadence with a 1-day mid-sector gap. */
function curve() {
  const t: number[] = [];
  for (const start of [1000, 1400]) {
    for (let x = 0; x < 10; x += 10 / 1440) if (Math.abs(x - 5) > 0.5) t.push(start + x);
  }
  return { t, f: t.map(() => 1) };
}

const det = (p: Partial<Detection>): Detection => ({ t0: 1001, duration_h: 2, depth_ppm: 1000, period_d: 3, kind: "periodic", outcome: "rejected", reason: "", ...p });

test("the tape shortens gaps to a fixed break and keeps data time linear inside a segment", () => {
  const tape = buildTape({ lightcurve: curve(), detections: [], sectors: [10, 24] });
  assert.equal(tape.segments.length, 4, "two sectors, each split by its download gap");
  assert.equal(tape.segments[0].x0, 0);
  const s1 = tape.segments[1];
  assert.ok(Math.abs(s1.x0 - (tape.segments[0].t1 - tape.segments[0].t0 + BREAK_TAPE_D)) < 1e-9);
  assert.ok(tape.length < 25, "a year's gap is not drawn as a year");
  assert.deepEqual(tape.segments.map((s) => s.sector), [10, 10, 24, 24]);
});

test("dips are marked only where there is data; the first of each signal is the labelled one", () => {
  const segs = buildTape({ lightcurve: curve(), detections: [], sectors: [10, 24] }).segments;
  const times = dipTimes(det({}), segs);
  assert.ok(times.every((tm) => segs.some((s) => tm >= s.t0 && tm <= s.t1)));
  assert.ok(!times.some((tm) => tm > 1011 && tm < 1400), "none in the year between sectors");
  assert.deepEqual(dipTimes(det({ kind: "single", period_d: null, t0: 1407.2 }), segs), [1407.2]);
  const tape = buildTape({ lightcurve: curve(), detections: [det({}), det({ t0: 1002, period_d: 4 })], sectors: [10, 24] });
  const firsts = tape.marks.filter((m) => m.first);
  assert.equal(firsts.length, 2);
  assert.ok(tape.marks.every((m, i) => i === 0 || m.x >= tape.marks[i - 1].x), "marks are in tape order");
  assert.equal(marksReached(tape, tape.marks[2].x).length, 3);
});

test("the pen eases in and out, and runs at the set speed in between", () => {
  const L = 27;
  const T = drawSeconds(L);
  assert.ok(Math.abs(T - (L / DAYS_PER_SECOND + RAMP_S)) < 1e-9);
  assert.equal(penAt(0, L), 0);
  assert.ok(Math.abs(penAt(T, L) - L) < 1e-9);
  const mid = T / 2;
  const v = (penAt(mid + 0.01, L) - penAt(mid - 0.01, L)) / 0.02;
  assert.ok(Math.abs(v - DAYS_PER_SECOND) < 1e-6, "cruise speed");
  const early = (penAt(0.02, L) - penAt(0, L)) / 0.02;
  assert.ok(early < DAYS_PER_SECOND / 10, "starts slowly");
  let prev = -1;
  for (let e = 0; e <= T; e += 0.05) {
    const x = penAt(e, L);
    assert.ok(x >= prev, "never goes back");
    prev = x;
  }
  // a very short tape still reaches its end without overshooting
  assert.ok(Math.abs(penAt(drawSeconds(0.5), 0.5) - 0.5) < 1e-9);
});

test("a star goes drawing, holding, advancing, done", () => {
  const L = 10;
  const T = drawSeconds(L);
  assert.equal(phaseAt(1, L).kind, "drawing");
  assert.equal(phaseAt(T + HOLD_S / 2, L).kind, "holding");
  assert.equal(phaseAt(T + HOLD_S + ADVANCE_S / 2, L).kind, "advancing");
  assert.equal(phaseAt(T + HOLD_S + ADVANCE_S + 0.1, L).kind, "done");
  assert.equal(easeInOut(0), 0);
  assert.equal(easeInOut(1), 1);
  assert.equal(easeInOut(0.5), 0.5);
});

test("the flux scale holds the deepest dip found and some air", () => {
  const f = Array.from({ length: 1000 }, (_, i) => 1 + ((i % 7) - 3) * 1e-4);
  const [top, bottom] = fluxRange(f, [det({ depth_ppm: 20000 })]);
  assert.ok(bottom < 0.98, "the 2% dip fits");
  assert.ok(top > 1.0003);
  assert.equal(lowerBound([1, 2, 3, 4], 2.5), 2);
});

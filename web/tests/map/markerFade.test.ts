import { test } from "node:test";
import assert from "node:assert/strict";
import { easeOut, leavers, MARKER_FADE_S, MAX_DT, stepFade } from "../../components/map/scene/markerFade.ts";
import type { Marker } from "../../lib/markers.ts";

const m = (id: string): Marker => ({ id, title: id, category: "transients", recency: 1, fresh: false, ra: 0, dec: 0, onSun: false });

test("markers the filters remove keep fading; ones that come back are live again", () => {
  const a = m("a"), b = m("b"), c = m("c");
  assert.deepEqual(leavers([a, b], [], [a]).map((x) => x.id), ["b"]);
  assert.deepEqual(leavers([a], [b], [a, b]).map((x) => x.id), [], "b returned mid-fade");
  assert.deepEqual(leavers([a, c], [b, c], [a]).map((x) => x.id), ["c", "b"], "no duplicates");
});

test("a fade takes MARKER_FADE_S (at most 240 ms) and ends exactly on 0 or 1", () => {
  assert.ok(MARKER_FADE_S <= 0.24);
  const progress = new Float32Array([0, 1]);
  const alpha = new Float32Array(2);
  let frames = 0;
  while (stepFade(progress, alpha, 1, 1 / 60, false)) frames++;
  assert.equal(frames + 1, Math.ceil(MARKER_FADE_S * 60), "about 14 frames at 60 fps");
  assert.deepEqual([...alpha], [1, 0]);
});

test("mid-fade, entering eases in and leaving drops away at once", () => {
  const progress = new Float32Array([0, 1]);
  const alpha = new Float32Array(2);
  stepFade(progress, alpha, 1, MARKER_FADE_S / 2, false);
  assert.ok(alpha[0] > 0.8, "arriving marker is mostly there by half time");
  assert.ok(alpha[1] < 0.2, "leaving marker is mostly gone by half time");
  assert.equal(easeOut(0), 0);
  assert.equal(easeOut(1), 1);
});

test("reduced motion is instant", () => {
  const progress = new Float32Array([0, 1]);
  const alpha = new Float32Array(2);
  assert.equal(stepFade(progress, alpha, 1, 1 / 60, true), false);
  assert.deepEqual([...alpha], [1, 0]);
});

test("a long gap (tab was hidden) resumes the fade instead of jumping to the end", () => {
  const progress = new Float32Array([0]);
  const alpha = new Float32Array(1);
  stepFade(progress, alpha, 1, 30, false);
  assert.ok(Math.abs(progress[0] - MAX_DT / MARKER_FADE_S) < 1e-6);
});

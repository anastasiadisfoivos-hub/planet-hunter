import { test } from "node:test";
import assert from "node:assert/strict";
import { cubicBezier, flightDuration, flightPose, type Pose } from "../components/map/scene/flight.ts";

const overview: Pose = { pos: [84, 30, 118], target: [0, 0, 0], fov: 55 };
const star: Pose = { pos: [10, 3.02, 5], target: [10, 3, 5], fov: 55 };
const dist = (p: Pose) => Math.hypot(p.pos[0] - p.target[0], p.pos[1] - p.target[1], p.pos[2] - p.target[2]);

test("cubicBezier hits its endpoints and is monotonic", () => {
  const e = cubicBezier(0.65, 0, 0.35, 1);
  assert.equal(e(0), 0);
  assert.equal(e(1), 1);
  let prev = 0;
  for (let x = 0.05; x <= 1; x += 0.05) {
    assert.ok(e(x) >= prev - 1e-9);
    prev = e(x);
  }
  assert.ok(Math.abs(e(0.5) - 0.5) < 1e-3);
});

test("flight starts at the start pose and ends exactly at the destination", () => {
  const a = flightPose(overview, star, 0);
  overview.pos.forEach((v, i) => assert.ok(Math.abs(a.pos[i] - v) < 1e-6));
  assert.deepEqual(flightPose(overview, star, 1), star);
});

test("flight pulls back before gliding in", () => {
  const near: Pose = { pos: [0, 0, 20], target: [0, 0, 0], fov: 55 };
  const far: Pose = { pos: [30, 0, 20], target: [30, 0, 0], fov: 55 };
  const peak = Math.max(...[0.2, 0.3, 0.35, 0.4].map((t) => dist(flightPose(near, far, t))));
  assert.ok(peak > 20 * 1.1, `peak distance ${peak}`);
});

test("the view turns before the camera closes in", () => {
  const mid = flightPose(overview, star, 0.5);
  // By halfway the target is most of the way to the star, but the camera is still far from it.
  const tDone = Math.hypot(mid.target[0] - 10, mid.target[1] - 3, mid.target[2] - 5) / Math.hypot(10, 3, 5);
  assert.ok(tDone < 0.35, `target ${tDone}`);
  assert.ok(dist(mid) > 1, `distance ${dist(mid)}`);
});

test("duration stays within 1.2 to 2 seconds", () => {
  const short: Pose = { pos: [0, 0, 20.5], target: [0, 0, 0.5], fov: 55 };
  const base: Pose = { pos: [0, 0, 20], target: [0, 0, 0], fov: 55 };
  for (const [a, b] of [
    [base, short],
    [overview, star],
    [star, overview],
  ] as const) {
    const d = flightDuration(a, b);
    assert.ok(d >= 1.2 && d <= 2, `duration ${d}`);
  }
  assert.ok(flightDuration(base, short) < 1.4);
  assert.ok(flightDuration(overview, star) > 1.7);
});

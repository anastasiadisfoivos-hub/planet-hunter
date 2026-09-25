import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import { createRig, flyTo, interrupt, stepFlight, type Rig } from "../components/map/scene/rig.ts";
import type { Pose } from "../components/map/scene/flight.ts";

/** camera-controls stand-in: setLookAt moves the camera and target immediately, like enableTransition=false. */
function rigWithFakeControls(reduced = false): Rig {
  const rig = createRig(reduced, 60);
  const camera = new THREE.PerspectiveCamera(60, 1.6, 0.05, 5000);
  const target = new THREE.Vector3();
  const controls = {
    minDistance: 0,
    maxDistance: Infinity,
    setLookAt(px: number, py: number, pz: number, tx: number, ty: number, tz: number) {
      camera.position.set(px, py, pz);
      target.set(tx, ty, tz);
      camera.lookAt(target);
    },
    getTarget(out: THREE.Vector3) {
      return out.copy(target);
    },
    get distance() {
      return camera.position.distanceTo(target);
    },
  };
  rig.camera = camera;
  rig.controls = controls as unknown as Rig["controls"];
  controls.setLookAt(0, 0, 150, 0, 0, 0);
  return rig;
}

/** The view from Earth toward a direction (what "Jump to" and "Show on map" use). */
const earth = (x: number, y: number, z: number, fov: number): Pose => {
  const l = Math.hypot(x, y, z);
  return { pos: [(-x / l) * 0.6, (-y / l) * 0.6, (-z / l) * 0.6], target: [0, 0, 0], fov };
};

function land(rig: Rig, t0: number) {
  let t = t0;
  while (stepFlight(rig, t)) t += 16;
}

function assertAt(rig: Rig, p: Pose) {
  const c = rig.camera!;
  assert.ok(c.position.distanceTo(new THREE.Vector3(...p.pos)) < 1e-9, `camera at ${c.position.toArray()} not ${p.pos}`);
  assert.equal(c.fov, p.fov);
}

test("jump, then jump again mid-flight: lands exactly on the second target", () => {
  const rig = rigWithFakeControls();
  const orion = earth(0.1, -0.09, -0.99, 12);
  const carina = earth(-0.25, -0.86, -0.44, 20);
  flyTo(rig, orion, "jump", 0);
  stepFlight(rig, 400); // part way
  flyTo(rig, carina, "jump", 400);
  land(rig, 400);
  assertAt(rig, carina);
});

test("the same jump repeated many times always lands on it", () => {
  const rig = rigWithFakeControls();
  const lagoon = earth(-0.02, -0.4, 0.92, 6);
  let t = 0;
  for (let i = 0; i < 5; i++) {
    flyTo(rig, lagoon, "jump", t);
    stepFlight(rig, t + 200 * i); // sometimes mid-flight, sometimes just started
    t += 200 * i + 16;
  }
  land(rig, t);
  assertAt(rig, lagoon);
});

test("alternating targets, each one after landing", () => {
  const rig = rigWithFakeControls();
  const a = earth(1, 0, 0, 30);
  const b = earth(0, 0, -1, 8);
  let t = 0;
  for (const p of [a, b, a, b, a]) {
    flyTo(rig, p, "jump", t);
    land(rig, t);
    assertAt(rig, p);
    t += 5000;
  }
});

test("interrupting stops where it is and keeps that field of view", () => {
  const rig = rigWithFakeControls();
  flyTo(rig, earth(1, 0, 0, 10), "jump", 0);
  stepFlight(rig, 500);
  const fov = rig.camera!.fov;
  interrupt(rig);
  assert.equal(rig.flight, null);
  assert.equal(rig.fovTarget, fov);
  assert.equal(stepFlight(rig, 600), false);
});

test("reduced motion: every jump is an instant cut", () => {
  const rig = rigWithFakeControls(true);
  const p = earth(0, 1, 0, 15);
  flyTo(rig, p, "jump", 0);
  assert.equal(rig.flight, null);
  assertAt(rig, p);
});

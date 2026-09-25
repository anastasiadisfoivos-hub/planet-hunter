// The camera rig: camera-controls (yomotsu) for damped orbit and dolly with inertia, plus our own
// eased fly-to on top (see flight.ts). Everything that moves the camera goes through here.

import * as THREE from "three";
import CameraControls from "camera-controls";
import { flightDuration, flightPose, type Pose, type V3 } from "./flight.ts";

CameraControls.install({ THREE });

export type FlightKind = "focus" | "back" | "jump";

export type Rig = {
  controls: CameraControls | null;
  camera: THREE.PerspectiveCamera | null;
  flight: { from: Pose; to: Pose; start: number; dur: number; kind: FlightKind } | null;
  /** Field of view the camera eases toward when not flying. */
  fovTarget: number;
  /** Where to return to when the close-up is closed. */
  saved: Pose | null;
  /** Animation clock in seconds; frozen under reduced motion, paused while the tab is hidden. */
  time: number;
  reduced: boolean;
  /** Distance limits for the current mode, applied when no flight is running. */
  limits: { min: number; max: number };
  hover: number;
  hoverT: number;
  selectedT: number;
};

export function createRig(reduced: boolean, fov: number): Rig {
  return { controls: null, camera: null, flight: null, fovTarget: fov, saved: null, time: 0, reduced, limits: { min: 0.3, max: 320 }, hover: -1, hoverT: 0, selectedT: 0 };
}

const tv = new THREE.Vector3();

export function currentPose(rig: Rig): Pose {
  const cam = rig.camera!;
  const t = rig.controls!.getTarget(tv, false);
  return { pos: [cam.position.x, cam.position.y, cam.position.z], target: [t.x, t.y, t.z], fov: cam.fov };
}

function setPose(rig: Rig, p: Pose) {
  rig.controls!.setLookAt(p.pos[0], p.pos[1], p.pos[2], p.target[0], p.target[1], p.target[2], false);
  if (rig.camera!.fov !== p.fov) {
    rig.camera!.fov = p.fov;
    rig.camera!.updateProjectionMatrix();
  }
}

/** Apply the mode's distance limits without snapping: widen them to include where the camera is now. */
export function applyLimits(rig: Rig) {
  const c = rig.controls!;
  const d = c.distance;
  c.minDistance = Math.min(rig.limits.min, d);
  c.maxDistance = Math.max(rig.limits.max, d);
}

/** Fly to a pose. Instant under reduced motion. */
export function flyTo(rig: Rig, to: Pose, kind: FlightKind, now = performance.now()) {
  if (!rig.controls || !rig.camera) return;
  rig.fovTarget = to.fov;
  if (rig.reduced) {
    rig.flight = null;
    setPose(rig, to);
    applyLimits(rig);
    return;
  }
  const from = currentPose(rig);
  // No limits mid-flight: the path legitimately passes distances outside either end's range.
  rig.controls.minDistance = 0;
  rig.controls.maxDistance = Infinity;
  rig.flight = { from, to, start: now, dur: flightDuration(from, to) * 1000, kind };
}

/** Stop a flight where it is (any user input does this). */
export function interrupt(rig: Rig) {
  if (!rig.flight || !rig.camera) return;
  rig.flight = null;
  rig.fovTarget = rig.camera.fov;
  applyLimits(rig);
}

/** Advance the flight. Returns true while one is running. */
export function stepFlight(rig: Rig, now: number): boolean {
  const f = rig.flight;
  if (!f) return false;
  const t = Math.min(1, (now - f.start) / f.dur);
  setPose(rig, flightPose(f.from, f.to, t));
  if (t >= 1) {
    rig.flight = null;
    applyLimits(rig);
  }
  return true;
}

export function pose(pos: V3, target: V3, fov: number): Pose {
  return { pos, target, fov };
}

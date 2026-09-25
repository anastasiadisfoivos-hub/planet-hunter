// Camera fly-to: one eased timeline with three overlapping stages.
//   1. pull back: the camera eases away from where it is (a hump on the distance curve);
//   2. rotate: the look-at target swings toward the destination first, so the view turns before it travels;
//   3. glide in: distance closes on the destination in log space, so 150 units to 0.002 units reads as one move.
// Pure math on plain tuples so it can be unit tested without three.js.

export type V3 = [number, number, number];
export type Pose = { pos: V3; target: V3; fov: number };

/** cubic-bezier(x1, y1, x2, y2) as an easing function of x in [0, 1]. */
export function cubicBezier(x1: number, y1: number, x2: number, y2: number): (x: number) => number {
  const bx = (t: number) => 3 * x1 * t * (1 - t) ** 2 + 3 * x2 * t * t * (1 - t) + t ** 3;
  const by = (t: number) => 3 * y1 * t * (1 - t) ** 2 + 3 * y2 * t * t * (1 - t) + t ** 3;
  const dbx = (t: number) => 3 * x1 * (1 - t) ** 2 + 6 * (x2 - x1) * t * (1 - t) + 3 * (1 - x2) * t * t;
  return (x: number) => {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    let t = x;
    for (let i = 0; i < 6; i++) {
      const d = dbx(t);
      if (Math.abs(d) < 1e-6) break;
      t = Math.min(1, Math.max(0, t - (bx(t) - x) / d));
    }
    return by(t);
  };
}

/** On-screen movement: strong ease-in-out. */
export const easeInOut = cubicBezier(0.65, 0, 0.35, 1);

const sub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const len = (a: V3) => Math.hypot(a[0], a[1], a[2]);
const lerp = (a: number, b: number, t: number) => a + (b - a) * t;
const clamp01 = (x: number) => Math.min(1, Math.max(0, x));
const smooth = (a: number, b: number, x: number) => {
  const t = clamp01((x - a) / (b - a));
  return t * t * (3 - 2 * t);
};

/** Spherical interpolation between two unit vectors. */
function slerp(a: V3, b: V3, t: number): V3 {
  const dot = Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]));
  const om = Math.acos(dot);
  if (om < 1e-4) return [lerp(a[0], b[0], t), lerp(a[1], b[1], t), lerp(a[2], b[2], t)];
  const s = Math.sin(om);
  const ka = Math.sin((1 - t) * om) / s;
  const kb = Math.sin(t * om) / s;
  return [a[0] * ka + b[0] * kb, a[1] * ka + b[1] * kb, a[2] * ka + b[2] * kb];
}

/** Flight length in seconds: 1.2 s for short hops, up to 2 s for long, wide moves. */
export function flightDuration(from: Pose, to: Pose): number {
  const d0 = Math.max(1e-6, len(sub(from.pos, from.target)));
  const d1 = Math.max(1e-6, len(sub(to.pos, to.target)));
  const scale = Math.abs(Math.log10(d0 / d1)) / 4; // orders of magnitude in distance
  const travel = len(sub(to.target, from.target)) / Math.max(d0, d1, 1e-6);
  const a = norm(sub(from.target, from.pos));
  const b = norm(sub(to.target, to.pos));
  const turn = Math.acos(Math.min(1, Math.max(-1, a[0] * b[0] + a[1] * b[1] + a[2] * b[2]))) / Math.PI;
  return 1.2 + 0.8 * clamp01(Math.max(scale, turn, Math.min(1, travel)));
}

function norm(a: V3): V3 {
  const l = len(a) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
}

/** The camera pose at time fraction t in [0, 1]. Returns exactly `to` at t = 1. */
export function flightPose(from: Pose, to: Pose, t: number): Pose {
  if (t >= 1) return to;
  const off0 = sub(from.pos, from.target);
  const off1 = sub(to.pos, to.target);
  const d0 = Math.max(1e-6, len(off0));
  const d1 = Math.max(1e-6, len(off1));
  const dir = slerp(norm(off0), norm(off1), easeInOut(t));

  // The target leads: the view turns toward the destination before the camera has travelled far.
  const eT = easeInOut(clamp01(t / 0.75));
  const target: V3 = [lerp(from.target[0], to.target[0], eT), lerp(from.target[1], to.target[1], eT), lerp(from.target[2], to.target[2], eT)];

  // Distance glides in log space, starting a little after the turn begins.
  const eD = easeInOut(clamp01((t - 0.15) / 0.85));
  // Pull back: up to +45% distance, peaking about a third of the way in, gone by 80%.
  const travel = len(sub(to.target, from.target));
  const hump = 0.45 * clamp01(travel / Math.max(d0, 1e-6)) * smooth(0, 0.35, t) * (1 - smooth(0.35, 0.8, t));
  const d = Math.exp(lerp(Math.log(d0), Math.log(d1), eD)) * (1 + hump);

  return {
    pos: [target[0] + dir[0] * d, target[1] + dir[1] * d, target[2] + dir[2] * d],
    target,
    fov: lerp(from.fov, to.fov, eD),
  };
}

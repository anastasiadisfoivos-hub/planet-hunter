import type { Sphere } from "@/lib/contract";
import type { DraftResult } from "@/state/store";
import { inFootprint, outsideReason, type Footprint, type HostsFile } from "./data";
import { radecToVec, separationDeg, type Vec3 } from "./sky";

export type HostIndex = { hosts: HostsFile; dirs: Vec3[] };

export function indexHosts(hosts: HostsFile): HostIndex {
  return { hosts, dirs: hosts.ra.map((ra, i) => radecToVec(ra, hosts.dec[i])) };
}

/** Star trap if a known host sits inside the sphere, sky trap if the patch is in Rubin's zone. */
export function classify(sphere: Sphere, idx: HostIndex, fp: Footprint): DraftResult {
  const c = radecToVec(sphere.ra_deg, sphere.dec_deg);
  const cosR = Math.cos((sphere.radius_deg * Math.PI) / 180);
  let best = -1;
  let bestSep = Infinity;
  let inside = 0;
  for (let i = 0; i < idx.dirs.length; i++) {
    const d = idx.dirs[i];
    // Cheap reject before the precise separation.
    if (d[0] * c[0] + d[1] * c[1] + d[2] * c[2] < cosR - 1e-9) continue;
    const sep = separationDeg(c, d);
    if (sep > sphere.radius_deg) continue;
    inside++;
    if (sep < bestSep) {
      bestSep = sep;
      best = i;
    }
  }
  if (best >= 0) {
    return {
      kind: "star",
      target: { tic_id: idx.hosts.tic[best] },
      hostIndex: best,
      name: idx.hosts.name[best],
      starsInside: inside,
    };
  }
  if (inFootprint(fp, sphere.ra_deg, sphere.dec_deg)) return { kind: "sky" };
  return { kind: "blocked", reason: outsideReason(sphere.ra_deg, sphere.dec_deg) };
}

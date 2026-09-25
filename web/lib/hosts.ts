import type { HostsFile } from "./data";
import { radecToVec, type Vec3 } from "./sky";

/** Planet hosts with their unit direction vectors, precomputed once. */
export type HostIndex = { hosts: HostsFile; dirs: Vec3[] };

export function indexHosts(hosts: HostsFile): HostIndex {
  return { hosts, dirs: hosts.ra.map((ra, i) => radecToVec(ra, hosts.dec[i])) };
}

// The planet-host list in /public/data/hosts.json (scripts/build-hosts.mjs): the finder's report links
// candidates on known hosts, and the top bar's star search reads it.

export type HostsFile = {
  source: string;
  distance_note: string;
  generated_at: string;
  count: number;
  dist_refs: string[];
  name: string[];
  tic: number[];
  gaia: string[];
  ra: number[];
  dec: number[];
  dist: number[];
  npl: number[];
  /** Known planet names per host (NASA Exoplanet Archive pl_name). */
  planets: string[][];
  teff: number[];
  /** Stellar radius in solar radii; 0 when not listed. */
  rad: number[];
  /** V magnitude from Earth; 99 when not listed. */
  vmag: number[];
  ref: number[];
};

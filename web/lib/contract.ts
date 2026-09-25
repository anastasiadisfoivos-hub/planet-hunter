// SHARED CONTRACT (identical across pipeline/, sources/, forecast/, api/, web/).
// Do not change this file on its own: a change here needs agreement across all five sessions.

/** A sky patch. radius_deg is 0.05 to 10. */
export type Sphere = { ra_deg: number; dec_deg: number; radius_deg: number };

export type StarTarget = { tic_id: number | string };

export const CATCH_TYPES = [
  "asteroid",
  "near_earth_object",
  "trans_neptunian_object",
  "comet",
  "interstellar_object",
  "supernova",
  "active_galaxy",
  "tidal_disruption_event",
  "microlensing",
  "kilonova",
  "variable_star",
  "flare",
  "eclipsing_binary",
  "planet_candidate",
  "unknown",
] as const;

export type CatchType = (typeof CATCH_TYPES)[number];

export type Discovery = {
  id: string;
  type: CatchType;
  /** 0 to 1 */
  confidence: number;
  source: "rubin" | "tess";
  origin: string;
  ra_deg: number;
  dec_deg: number;
  detected_at: string;
  name_if_known: string | null;
  known_status: "known" | "not_on_lists" | "unchecked";
  cutouts: { before: string; now: string; difference: string };
  light_curve?: unknown;
  explanation: string;
  links: { label: string; url: string }[];
  raw: unknown;
};

export type Forecast = {
  sphere: Sphere;
  window: { start: string; end: string };
  rubin_visit_probability: number;
  visits: { time: string; band: string }[];
  expected: { type: CatchType; mean_count: number }[];
  known_solar_system_objects: { name: string; type: CatchType; ra_deg: number; dec_deg: number }[];
  generated_at: string;
  inputs_used: string[];
};

/** heatmap.json */
export type Heatmap = {
  generated_at: string;
  /** "healpix nside=N" */
  grid: string;
  cells: { pix: number; counts: Partial<Record<CatchType, number>> }[];
};

export const SPHERE_RADIUS_MIN = 0.05;
export const SPHERE_RADIUS_MAX = 10;

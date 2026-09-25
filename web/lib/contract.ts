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

// ---------------------------------------------------------------------------------------------
// SHARED EVENT CONTRACT (mirrors events/src/skyevents/models.py). Additive update 2026-09-25:
// Image gains `thumb_url`, and ImageKind gains "forecast_map" (NOAA aurora model maps).

export const EVENT_TYPES = [
  "supernova",
  "tidal_disruption_event",
  "kilonova",
  "nova",
  "active_galaxy_flare",
  "variable_star",
  "stellar_flare",
  "microlensing",
  "asteroid",
  "near_earth_object",
  "comet",
  "interstellar_object",
  "gamma_ray_burst",
  "neutrino",
  "gravitational_wave",
  "fireball",
  "solar_flare",
  "coronal_mass_ejection",
  "geomagnetic_storm",
  "unknown",
] as const;

export type EventType = (typeof EVENT_TYPES)[number];

export type ImageKind =
  | "cutout_reference"
  | "cutout_new"
  | "cutout_difference"
  | "sky_context"
  | "solar"
  | "light_curve"
  /** A model forecast map (NOAA aurora), not a photograph. */
  | "forecast_map";

export type Image = {
  url: string;
  /** Small version for feed rows; null when the source has none. */
  thumb_url: string | null;
  kind: ImageKind;
  caption: string;
  credit: string;
  license: string;
  width: number | null;
  height: number | null;
};

export type ConfidenceBasis = "official_report" | "catalogue_match" | "machine_guess";

export type EventLocation =
  | { frame: "sky"; ra_deg: number; dec_deg: number; error_deg: number }
  | { frame: "sun" }
  | { frame: "earth"; lat_deg: number; lon_deg: number; alt_km: number | null };

export type SkyEvent = {
  /** "<source>:<source's own id>", stable */
  id: string;
  type: EventType;
  title: string;
  /** Plain English, 1 to 2 sentences. */
  summary: string;
  source: string;
  source_url: string;
  /** ISO 8601 UTC */
  observed_at: string;
  /** ISO 8601 UTC */
  reported_at: string;
  location: EventLocation;
  /** 0 to 1 */
  confidence: number;
  confidence_basis: ConfidenceBasis;
  brightness_mag: number | null;
  images: Image[];
  raw: Record<string, unknown>;
};

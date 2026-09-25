// Event filtering, counting and labelling. Pure functions, shared by the mock API, the filter
// panel's counts and the map, so all three always agree.

import { CATEGORIES, CATEGORY_OF, EVENT_TYPES, type Category, type EventType, type SkyEvent } from "./contract.ts";

export type TimeRange = { kind: "24h" } | { kind: "7d" } | { kind: "30d" } | { kind: "custom"; start: string; end: string };

export type EventFilters = {
  /** Types to show. All types by default. */
  types: EventType[];
  /** On observed_at. Default 7 days. */
  time: TimeRange;
  /** Sources to show; an empty list means every source. */
  sources: string[];
  /** 0 to 1 */
  minConfidence: number;
  withPictures: boolean;
  /**
   * Rubin's alert stream is paused; the events service fills in with Rubin's latest nights at their
   * real (older) dates, flagged raw.from_latest_observed_window. Those stay out of the time-based
   * feed and are shown only with this toggle.
   */
  rubinLatest: boolean;
};

export const DEFAULT_FILTERS: EventFilters = {
  types: [...EVENT_TYPES],
  time: { kind: "7d" },
  sources: [],
  minConfidence: 0,
  withPictures: false,
  rubinLatest: false,
};

const HOUR = 3600_000;

/** [start, end] in ms for a time range, relative to `now`. */
export function timeWindow(t: TimeRange, now: number): [number, number] {
  switch (t.kind) {
    case "24h":
      return [now - 24 * HOUR, now];
    case "7d":
      return [now - 7 * 24 * HOUR, now];
    case "30d":
      return [now - 30 * 24 * HOUR, now];
    case "custom":
      return [Date.parse(t.start), Date.parse(t.end)];
  }
}

export function isRubinLatest(e: SkyEvent): boolean {
  return e.raw?.from_latest_observed_window === true;
}

type Skip = { types?: boolean; sources?: boolean };

/** Does an event pass the filters? `skip` ignores one facet, for "how many would I get" counts. */
export function matches(e: SkyEvent, f: EventFilters, now: number, skip: Skip = {}): boolean {
  if (!skip.types && !f.types.includes(e.type)) return false;
  if (!skip.sources && f.sources.length > 0 && !f.sources.includes(e.source)) return false;
  if (e.confidence < f.minConfidence) return false;
  if (f.withPictures && e.images.length === 0) return false;
  if (isRubinLatest(e)) return f.rubinLatest;
  const [start, end] = timeWindow(f.time, now);
  const t = Date.parse(e.observed_at);
  return t >= start && t <= end;
}

/** Matching events, newest first (ties broken by id, so paging is stable). */
export function applyFilters(events: SkyEvent[], f: EventFilters, now: number): SkyEvent[] {
  return events
    .filter((e) => matches(e, f, now))
    .sort((a, b) => b.observed_at.localeCompare(a.observed_at) || a.id.localeCompare(b.id));
}

/** Per-type counts under every other filter, so each checkbox says what ticking it would add. */
export function countByType(events: SkyEvent[], f: EventFilters, now: number): Record<EventType, number> {
  const out = Object.fromEntries(EVENT_TYPES.map((t) => [t, 0])) as Record<EventType, number>;
  for (const e of events) if (matches(e, f, now, { types: true })) out[e.type]++;
  return out;
}

export function countBySource(events: SkyEvent[], f: EventFilters, now: number): Record<string, number> {
  const out: Record<string, number> = {};
  for (const e of events) if (matches(e, f, now, { sources: true })) out[e.source] = (out[e.source] ?? 0) + 1;
  return out;
}

/** Page through a list with an opaque numeric cursor. */
export function page<T>(items: T[], cursor: string | null, limit: number): { items: T[]; next: string | null } {
  const start = cursor ? Number(cursor) : 0;
  const end = start + limit;
  return { items: items.slice(start, end), next: end < items.length ? String(end) : null };
}

/** 1 for an event observed just now, easing down to 0.35 at 30 days and older. */
export function recency(observedAt: string, now: number): number {
  const days = Math.max(0, (now - Date.parse(observedAt)) / (24 * HOUR));
  return 0.35 + 0.65 * Math.max(0, 1 - Math.log10(1 + days) / Math.log10(31));
}

export const CATEGORY_LABEL: Record<Category, string> = {
  transients: "Transients",
  solar_system: "Solar system",
  sun_space_weather: "Sun & space weather",
  earth_atmosphere: "Earth atmosphere",
  high_energy: "High energy",
  other: "Other",
};

export const TYPE_LABEL: Record<EventType, string> = {
  supernova: "Supernova",
  tidal_disruption_event: "Tidal disruption event",
  kilonova: "Kilonova",
  nova: "Nova",
  active_galaxy_flare: "Active galaxy flare",
  variable_star: "Variable star",
  stellar_flare: "Stellar flare",
  microlensing: "Microlensing",
  asteroid: "Asteroid",
  near_earth_object: "Near-Earth object",
  comet: "Comet",
  interstellar_object: "Interstellar object",
  gamma_ray_burst: "Gamma-ray burst",
  neutrino: "Neutrino",
  gravitational_wave: "Gravitational wave",
  fireball: "Fireball",
  solar_flare: "Solar flare",
  coronal_mass_ejection: "Coronal mass ejection",
  geomagnetic_storm: "Geomagnetic storm",
  unknown: "Unclassified",
};

export const BASIS_LABEL: Record<SkyEvent["confidence_basis"], string> = {
  official_report: "official report",
  catalogue_match: "catalogue match",
  machine_guess: "machine guess",
};

/** Display names for the events service's source keys. */
export const SOURCE_LABEL: Record<string, string> = {
  rubin: "Rubin",
  ztf: "ZTF",
  tns: "TNS",
  mpc: "Minor Planet Center",
  jpl: "JPL",
  cneos: "CNEOS",
  donki: "NASA DONKI",
  gcn: "GCN",
  icecube: "IceCube",
  gracedb: "GraceDB",
};

export function categoryOf(t: EventType): Category {
  return CATEGORY_OF[t];
}

export { CATEGORIES };

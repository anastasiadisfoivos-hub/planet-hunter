// Filters in the address bar, so a filtered view can be shared. Only settings that differ from the
// defaults are written, so an unfiltered map keeps a clean URL, and every other parameter (host,
// bright, fps, nodetail) is left exactly as it was.
//
//   time=24h|30d|custom   from=YYYY-MM-DD&to=YYYY-MM-DD (custom only)
//   types=transients,gamma_ray_burst   a whole category by its key, otherwise single types; "none" for nothing
//   src=ztf,tns   conf=50 (percent)   pics=1   rubin=1

import { CATEGORIES, EVENT_TYPES, type Category, type EventType } from "../../lib/contract.ts";
import { DEFAULT_FILTERS, type EventFilters } from "../../lib/events.ts";
import { CATEGORY_KEYS, chipState } from "./filterModel.ts";

export const FILTER_KEYS = ["time", "from", "to", "types", "src", "conf", "pics", "rubin"] as const;

const DAY = /^\d{4}-\d{2}-\d{2}$/;

export function filtersFromParams(p: URLSearchParams): EventFilters {
  const f: EventFilters = { ...DEFAULT_FILTERS };

  const time = p.get("time");
  if (time === "24h" || time === "30d") f.time = { kind: time };
  else if (time === "custom") {
    const from = p.get("from") ?? "";
    const to = p.get("to") ?? "";
    if (DAY.test(from) && DAY.test(to) && from <= to) f.time = { kind: "custom", start: `${from}T00:00:00Z`, end: `${to}T23:59:59Z` };
  }

  const types = p.get("types");
  if (types !== null) {
    const out = new Set<EventType>();
    for (const k of types.split(",")) {
      if (k in CATEGORIES) for (const t of CATEGORIES[k as Category]) out.add(t);
      else if ((EVENT_TYPES as readonly string[]).includes(k)) out.add(k as EventType);
    }
    f.types = EVENT_TYPES.filter((t) => out.has(t));
  }

  const src = p.get("src");
  if (src) f.sources = src.split(",").filter(Boolean);

  const conf = Number(p.get("conf"));
  if (conf > 0 && conf <= 100) f.minConfidence = conf / 100;

  if (p.get("pics") === "1") f.withPictures = true;
  if (p.get("rubin") === "1") f.rubinLatest = true;
  return f;
}

/** A copy of `base` with the filter parameters rewritten for `f`. Other parameters are untouched. */
export function paramsWithFilters(f: EventFilters, base: URLSearchParams): URLSearchParams {
  const p = new URLSearchParams(base);
  for (const k of FILTER_KEYS) p.delete(k);

  if (f.time.kind !== DEFAULT_FILTERS.time.kind) p.set("time", f.time.kind);
  if (f.time.kind === "custom") {
    p.set("from", f.time.start.slice(0, 10));
    p.set("to", f.time.end.slice(0, 10));
  }

  if (!EVENT_TYPES.every((t) => f.types.includes(t))) {
    const parts: string[] = [];
    for (const c of CATEGORY_KEYS) {
      const st = chipState(f, c);
      if (st === "on") parts.push(c);
      else if (st === "mixed") parts.push(...CATEGORIES[c].filter((t) => f.types.includes(t)));
    }
    p.set("types", parts.length ? parts.join(",") : "none");
  }

  if (f.sources.length) p.set("src", [...f.sources].sort().join(","));
  if (f.minConfidence > 0) p.set("conf", String(Math.round(f.minConfidence * 100)));
  if (f.withPictures) p.set("pics", "1");
  if (f.rubinLatest) p.set("rubin", "1");
  return p;
}

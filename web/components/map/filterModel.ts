// What the floating filter bar shows and does, as pure functions over EventFilters, so the bar, the
// "More" badge, Reset and the tests all agree. No React, no DOM.

import { CATEGORIES, type Category, type EventType, type SkyEvent } from "../../lib/contract.ts";
import { countByType, DEFAULT_FILTERS, type EventFilters } from "../../lib/events.ts";

export const CATEGORY_KEYS = Object.keys(CATEGORIES) as Category[];

const typesOf = (c: Category) => CATEGORIES[c] as readonly EventType[];

/** A chip is on (every type ticked), off (none) or mixed (some, set in "More"). */
export type ChipState = "on" | "off" | "mixed";

export function chipState(f: EventFilters, c: Category): ChipState {
  const on = typesOf(c).filter((t) => f.types.includes(t)).length;
  return on === 0 ? "off" : on === typesOf(c).length ? "on" : "mixed";
}

/** Tapping a chip: an "on" chip turns its whole category off; "off" or "mixed" turns it all on. */
export function toggleCategory(f: EventFilters, c: Category): Partial<EventFilters> {
  const types = typesOf(c);
  const next = new Set(f.types);
  const turnOn = chipState(f, c) !== "on";
  for (const t of types) {
    if (turnOn) next.add(t);
    else next.delete(t);
  }
  return { types: [...next] };
}

/** Tick or untick single types (the sub-type list in "More"). */
export function setTypes(f: EventFilters, types: readonly EventType[], on: boolean): Partial<EventFilters> {
  const next = new Set(f.types);
  for (const t of types) {
    if (on) next.add(t);
    else next.delete(t);
  }
  return { types: [...next] };
}

/**
 * Per-chip counts: how many events the category has under every other filter (time range, sources,
 * confidence, pictures), so a chip says what turning it on would show.
 */
export function categoryCounts(events: SkyEvent[], f: EventFilters, now: number): Record<Category, number> {
  const byType = countByType(events, f, now);
  return Object.fromEntries(CATEGORY_KEYS.map((c) => [c, typesOf(c).reduce((n, t) => n + byType[t], 0)])) as Record<Category, number>;
}

/** Non-default settings that live inside "More": each mixed category, then one each for the rest. */
export function moreCount(f: EventFilters): number {
  let n = CATEGORY_KEYS.filter((c) => chipState(f, c) === "mixed").length;
  if (f.sources.length > 0) n++;
  if (f.minConfidence > 0) n++;
  if (f.withPictures) n++;
  if (f.time.kind === "custom") n++;
  if (f.rubinLatest) n++;
  return n;
}

/** True when the filters are the defaults (type order does not matter). Reset shows otherwise. */
export function isDefault(f: EventFilters): boolean {
  const d = DEFAULT_FILTERS;
  const sameTypes = f.types.length === d.types.length && d.types.every((t) => f.types.includes(t));
  return (
    sameTypes &&
    f.time.kind === d.time.kind &&
    f.sources.length === 0 &&
    f.minConfidence === d.minConfidence &&
    f.withPictures === d.withPictures &&
    f.rubinLatest === d.rubinLatest
  );
}

/** The feed's one line when the filters hide every event, with a "Clear filters" button. */
export const EMPTY_TITLE = "No events match these filters";
export const CLEAR_LABEL = "Clear filters";

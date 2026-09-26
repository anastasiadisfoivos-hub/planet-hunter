import { test } from "node:test";
import assert from "node:assert/strict";
import { applyFilters, DEFAULT_FILTERS, type EventFilters } from "../../lib/events.ts";
import { EVENT_TYPES, type SkyEvent } from "../../lib/contract.ts";
import { categoryCounts, chipState, CLEAR_LABEL, EMPTY_TITLE, isDefault, moreCount, setTypes, toggleCategory } from "../../components/map/filterModel.ts";
import { filtersFromParams, paramsWithFilters } from "../../components/map/urlFilters.ts";

const NOW = Date.parse("2026-09-25T16:03:00Z");
const HOUR = 3600_000;
const ev = (id: string, over: Partial<SkyEvent>): SkyEvent => ({
  id,
  type: "supernova",
  title: "t",
  summary: "s",
  source: "ztf",
  source_url: "https://x",
  observed_at: new Date(NOW - 2 * HOUR).toISOString(),
  reported_at: new Date(NOW - 2 * HOUR).toISOString(),
  location: { frame: "sky", ra_deg: 10, dec_deg: -5, error_deg: 0.001 },
  confidence: 0.8,
  confidence_basis: "machine_guess",
  brightness_mag: null,
  images: [],
  raw: {},
  ...over,
});
const ago = (h: number) => new Date(NOW - h * HOUR).toISOString();

const EVENTS: SkyEvent[] = [
  ev("sn1", {}),
  ev("sn2", { observed_at: ago(3 * 24) }),
  ev("tde", { type: "tidal_disruption_event", observed_at: ago(20 * 24) }),
  ev("neo", { type: "near_earth_object", source: "cneos" }),
  ev("comet", { type: "comet", source: "mpc", observed_at: ago(5 * 24) }),
  ev("grb", { type: "gamma_ray_burst", source: "gcn", confidence: 0.4 }),
  ev("flare", { type: "solar_flare", source: "donki", observed_at: ago(26) }),
];
const f = (over: Partial<EventFilters> = {}): EventFilters => ({ ...DEFAULT_FILTERS, ...over });
const apply = (cur: EventFilters, patch: Partial<EventFilters>): EventFilters => ({ ...cur, ...patch });

test("chip toggle: turning Transients off updates the URL and the events shown", () => {
  const start = f();
  assert.equal(chipState(start, "transients"), "on");
  const off = apply(start, toggleCategory(start, "transients"));
  assert.equal(chipState(off, "transients"), "off");

  const p = paramsWithFilters(off, new URLSearchParams("host=261136679&fps"));
  assert.equal(p.get("types"), "solar_system,sun_space_weather,earth_atmosphere,high_energy,other");
  assert.equal(p.get("host"), "261136679", "other parameters are kept");
  assert.ok(p.has("fps"));
  assert.deepEqual(new Set(filtersFromParams(p).types), new Set(off.types), "the link opens the same filters");

  assert.equal(applyFilters(EVENTS, start, NOW).length, 6);
  // Newest first; same time breaks ties by id.
  assert.deepEqual(
    applyFilters(EVENTS, off, NOW).map((e) => e.id),
    ["grb", "neo", "flare", "comet"],
  );

  // Toggling back is lossless and clears the parameter.
  const on = apply(off, toggleCategory(off, "transients"));
  assert.equal(paramsWithFilters(on, new URLSearchParams()).has("types"), false);
});

test("chip counts follow the time range, and say what a chip would add even when it is off", () => {
  const week = categoryCounts(EVENTS, f(), NOW);
  assert.equal(week.transients, 2);
  assert.equal(week.solar_system, 2);
  assert.equal(week.sun_space_weather, 1);
  assert.equal(week.high_energy, 1);
  assert.equal(week.earth_atmosphere, 0, "zero-count chips stay (dimmed)");

  const day = categoryCounts(EVENTS, f({ time: { kind: "24h" } }), NOW);
  assert.equal(day.transients, 1);
  assert.equal(day.solar_system, 1);
  assert.equal(day.sun_space_weather, 0);

  const month = categoryCounts(EVENTS, f({ time: { kind: "30d" } }), NOW);
  assert.equal(month.transients, 3);

  const off = apply(f(), toggleCategory(f(), "transients"));
  assert.equal(categoryCounts(EVENTS, off, NOW).transients, 2, "an off chip still shows its count");
  assert.equal(categoryCounts(EVENTS, f({ minConfidence: 0.5 }), NOW).high_energy, 0, "other filters apply");
});

test("a mixed chip turns fully on when tapped, and is written type by type in the URL", () => {
  const mixed = apply(f(), setTypes(f(), ["comet"], false));
  assert.equal(chipState(mixed, "solar_system"), "mixed");
  assert.equal(paramsWithFilters(mixed, new URLSearchParams()).get("types"), "transients,asteroid,near_earth_object,interstellar_object,sun_space_weather,earth_atmosphere,high_energy,other");
  const tapped = apply(mixed, toggleCategory(mixed, "solar_system"));
  assert.equal(chipState(tapped, "solar_system"), "on");
});

test("URL: time, custom dates, sources, confidence, pictures and Rubin round-trip; defaults write nothing", () => {
  assert.equal(paramsWithFilters(f(), new URLSearchParams("bright=12")).toString(), "bright=12");
  const all = f({
    time: { kind: "custom", start: "2026-07-01T00:00:00Z", end: "2026-07-31T23:59:59Z" },
    sources: ["ztf", "gcn"],
    minConfidence: 0.45,
    withPictures: true,
    rubinLatest: true,
  });
  const p = paramsWithFilters(all, new URLSearchParams());
  assert.equal(p.get("time"), "custom");
  assert.equal(p.get("from"), "2026-07-01");
  assert.equal(p.get("to"), "2026-07-31");
  assert.equal(p.get("src"), "gcn,ztf");
  assert.equal(p.get("conf"), "45");
  const back = filtersFromParams(p);
  assert.deepEqual(back.time, all.time);
  assert.deepEqual(new Set(back.sources), new Set(all.sources));
  assert.equal(back.minConfidence, 0.45);
  assert.equal(back.withPictures, true);
  assert.equal(back.rubinLatest, true);
  assert.deepEqual(filtersFromParams(new URLSearchParams("time=24h")).time, { kind: "24h" });
  assert.deepEqual(filtersFromParams(new URLSearchParams("time=custom&from=bad&to=2026-01-01")).time, DEFAULT_FILTERS.time, "bad dates fall back");
  assert.deepEqual(filtersFromParams(new URLSearchParams("types=none")).types, []);
  assert.deepEqual(filtersFromParams(new URLSearchParams("")), DEFAULT_FILTERS);
});

test("More badge counts the non-default settings inside More only", () => {
  assert.equal(moreCount(f()), 0);
  assert.equal(moreCount(f({ time: { kind: "24h" } })), 0, "time presets are on the bar");
  assert.equal(moreCount(apply(f(), toggleCategory(f(), "transients"))), 0, "whole chips are on the bar");
  assert.equal(moreCount(apply(f(), setTypes(f(), ["comet"], false))), 1, "a mixed category");
  assert.equal(moreCount(apply(f(), setTypes(f(), ["comet", "nova"], false))), 2, "one per mixed category");
  assert.equal(
    moreCount(f({ sources: ["ztf"], minConfidence: 0.5, withPictures: true, rubinLatest: true, time: { kind: "custom", start: "2026-01-01T00:00:00Z", end: "2026-01-02T23:59:59Z" } })),
    5,
  );
});

test("Reset shows only when something differs from the default", () => {
  assert.equal(isDefault(f()), true);
  assert.equal(isDefault(f({ types: [...EVENT_TYPES].reverse() })), true, "type order does not matter");
  assert.equal(isDefault(f({ time: { kind: "24h" } })), false);
  assert.equal(isDefault(apply(f(), toggleCategory(f(), "other"))), false);
  assert.equal(isDefault(f({ withPictures: true })), false);
  assert.equal(isDefault(f({ sources: ["ztf"] })), false);
  const back = apply(apply(f(), toggleCategory(f(), "other")), toggleCategory(apply(f(), toggleCategory(f(), "other")), "other"));
  assert.equal(isDefault(back), true, "toggling back hides Reset again");
});

test("empty state: all chips off hides every event; the feed says so with one action", () => {
  let cur = f();
  for (const c of ["transients", "solar_system", "sun_space_weather", "earth_atmosphere", "high_energy", "other"] as const) cur = apply(cur, toggleCategory(cur, c));
  assert.equal(applyFilters(EVENTS, cur, NOW).length, 0);
  assert.equal(paramsWithFilters(cur, new URLSearchParams()).get("types"), "none");
  assert.equal(isDefault(cur), false);
  assert.equal(EMPTY_TITLE, "No events match these filters");
  assert.equal(CLEAR_LABEL, "Clear filters");
});

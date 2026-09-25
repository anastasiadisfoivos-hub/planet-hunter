import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { applyFilters, countBySource, countByType, DEFAULT_FILTERS, matches, page, recency, timeWindow, type EventFilters } from "../lib/events.ts";
import { CATEGORIES, CATEGORY_OF, EVENT_TYPES, type SkyEvent } from "../lib/contract.ts";

const NOW = Date.parse("2026-09-25T16:03:00Z");
const ev = (over: Partial<SkyEvent>): SkyEvent => ({
  id: "x:1",
  type: "supernova",
  title: "t",
  summary: "s",
  source: "ztf",
  source_url: "https://x",
  observed_at: "2026-09-24T00:00:00Z",
  reported_at: "2026-09-24T00:00:00Z",
  location: { frame: "sky", ra_deg: 10, dec_deg: -5, error_deg: 0.001 },
  confidence: 0.8,
  confidence_basis: "machine_guess",
  brightness_mag: null,
  images: [],
  raw: {},
  ...over,
});
const f = (over: Partial<EventFilters> = {}): EventFilters => ({ ...DEFAULT_FILTERS, ...over });

test("every type sits in exactly one category", () => {
  const all = Object.values(CATEGORIES).flat();
  assert.equal(all.length, EVENT_TYPES.length);
  assert.deepEqual(new Set(all), new Set(EVENT_TYPES));
  assert.equal(CATEGORY_OF.fireball, "earth_atmosphere");
});

test("time ranges filter on observed_at", () => {
  assert.ok(matches(ev({ observed_at: "2026-09-25T00:00:00Z" }), f({ time: { kind: "24h" } }), NOW));
  assert.ok(!matches(ev({ observed_at: "2026-09-23T00:00:00Z" }), f({ time: { kind: "24h" } }), NOW));
  assert.ok(matches(ev({ observed_at: "2026-09-19T00:00:00Z", reported_at: "2026-09-25T00:00:00Z" }), f(), NOW));
  assert.ok(!matches(ev({ observed_at: "2026-09-17T00:00:00Z", reported_at: "2026-09-25T00:00:00Z" }), f(), NOW), "reported_at is not used");
  assert.ok(matches(ev({ observed_at: "2026-09-01T00:00:00Z" }), f({ time: { kind: "30d" } }), NOW));
  const custom = f({ time: { kind: "custom", start: "2017-08-01T00:00:00Z", end: "2017-09-01T00:00:00Z" } });
  assert.ok(matches(ev({ observed_at: "2017-08-17T12:41:04Z" }), custom, NOW));
  assert.deepEqual(timeWindow({ kind: "7d" }, NOW), [NOW - 7 * 86400000, NOW]);
});

test("types, sources, confidence and pictures", () => {
  assert.ok(!matches(ev({}), f({ types: ["comet"] }), NOW));
  assert.ok(matches(ev({}), f({ sources: ["ztf", "tns"] }), NOW));
  assert.ok(!matches(ev({}), f({ sources: ["tns"] }), NOW));
  assert.ok(!matches(ev({ confidence: 0.5 }), f({ minConfidence: 0.6 }), NOW));
  assert.ok(!matches(ev({}), f({ withPictures: true }), NOW));
  const img = { url: "u", thumb_url: null, kind: "sky_context" as const, caption: "", credit: "", license: "", width: null, height: null };
  assert.ok(matches(ev({ images: [img] }), f({ withPictures: true }), NOW));
});

test("Rubin's latest nights show only with their toggle, whatever their date", () => {
  const july = ev({ source: "rubin", observed_at: "2026-07-14T10:03:00Z", raw: { from_latest_observed_window: true } });
  assert.ok(!matches(july, f(), NOW));
  assert.ok(matches(july, f({ rubinLatest: true }), NOW));
  assert.ok(matches(july, f({ rubinLatest: true, time: { kind: "24h" } }), NOW));
  assert.ok(!matches(july, f({ rubinLatest: true, types: ["comet"] }), NOW));
});

test("newest first, stable paging", () => {
  const list = [ev({ id: "a", observed_at: "2026-09-20T00:00:00Z" }), ev({ id: "b", observed_at: "2026-09-24T00:00:00Z" }), ev({ id: "c", observed_at: "2026-09-24T00:00:00Z" })];
  assert.deepEqual(applyFilters(list, f(), NOW).map((e) => e.id), ["b", "c", "a"]);
  const p1 = page(["a", "b", "c"], null, 2);
  assert.deepEqual(p1, { items: ["a", "b"], next: "2" });
  assert.deepEqual(page(["a", "b", "c"], p1.next, 2), { items: ["c"], next: null });
});

test("counts ignore their own facet but respect the others", () => {
  const list = [ev({ id: "a" }), ev({ id: "b", type: "comet", source: "mpc" }), ev({ id: "c", type: "comet", confidence: 0.1 })];
  const flt = f({ types: ["supernova"], minConfidence: 0.5 });
  const byType = countByType(list, flt, NOW);
  assert.equal(byType.comet, 1);
  assert.equal(byType.supernova, 1);
  assert.deepEqual(countBySource(list, flt, NOW), { ztf: 1 });
});

test("recency: 1 now, fading to 0.35 by 30 days", () => {
  assert.ok(Math.abs(recency("2026-09-25T16:03:00Z", NOW) - 1) < 1e-9);
  assert.ok(recency("2026-09-24T16:03:00Z", NOW) > recency("2026-09-18T16:03:00Z", NOW));
  assert.equal(recency("2026-01-01T00:00:00Z", NOW), 0.35);
});

test("the mock: real events, every category, all contract-shaped", () => {
  const { meta, events } = JSON.parse(readFileSync(new URL("../public/data/events.mock.json", import.meta.url), "utf8"));
  assert.equal(meta.demo, true);
  assert.ok(events.length >= 55 && events.length <= 70);
  const cats = new Set(events.map((e: SkyEvent) => CATEGORY_OF[e.type]));
  assert.deepEqual(cats, new Set(Object.keys(CATEGORIES)));
  for (const e of events as SkyEvent[]) {
    assert.ok(EVENT_TYPES.includes(e.type));
    assert.ok(["official_report", "catalogue_match", "machine_guess"].includes(e.confidence_basis));
    for (const img of e.images) assert.ok("thumb_url" in img && img.url.startsWith("https://"));
  }
  const now = Date.parse(meta.recorded_until);
  assert.ok(applyFilters(events, DEFAULT_FILTERS, now).length >= 25, "the default 7 days is not empty");
});

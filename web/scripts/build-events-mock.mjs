// Build web/public/data/events.mock.json and web/public/data/status.mock.json from REAL recorded data.
//
//   node web/scripts/build-events-mock.mjs <dir>
//
// <dir> must hold:
//   events.json, status.json  skyevents.ingest() run offline on the recorded real week
//                             (events/tests/fixtures/http/live_week.json, 2026-09-18 to 2026-09-25),
//                             exactly as events/tests/test_live_week.py does;
//   example_events.json,      the PICTURES session's 20 real example events (one per type) and
//   example_pictures.json     their verified pictures (images/tests/fixtures, see images/EXAMPLES.md).
//
// Nothing is invented: every event, position, time and picture URL comes from those files. The mock is
// about 60 events: all 20 examples (every type, with pictures), plus a spread of the real week across
// sources and types, including some of Rubin's latest nights (raw.from_latest_observed_window).

import { readFile, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const out = path.join(here, "..", "public", "data");
const dir = process.argv[2];
if (!dir) throw new Error("usage: node build-events-mock.mjs <dir with events.json, status.json, example_*.json>");
const read = async (f) => JSON.parse(await readFile(path.join(dir, f), "utf8"));

const week = await read("events.json");
const status = await read("status.json");
const examples = await read("example_events.json");
const pictures = (await read("example_pictures.json")).pictures;

const BASES = new Set(["official_report", "catalogue_match", "machine_guess"]);
const byId = new Map(week.map((e) => [e.id, e]));

/** The example fixture predates the confidence_basis enum: map its free text onto the contract values. */
function basis(e) {
  if (BASES.has(e.confidence_basis)) return e.confidence_basis;
  return /^Fink class/.test(e.confidence_basis) ? "machine_guess" : "official_report";
}

/** Contract Image, with thumb_url (null where the source gave no thumbnail). */
const image = (img) => ({ thumb_url: null, ...img });

function smallRaw(raw) {
  const keep = {};
  for (const [k, v] of Object.entries(raw ?? {})) {
    if (JSON.stringify(v).length <= 200) keep[k] = v;
  }
  return keep;
}

// Rubin is paused: the events service serves its latest nights (status.sources.rubin.window) with
// raw.from_latest_observed_window = true. The example fixture predates that flag (and uses an older id
// form), so set it the same way for any Rubin event observed inside that window.
const rubinWindow = status.sources.rubin?.window;
function rubinLatest(e) {
  if (!rubinWindow || e.id.split(":")[0] !== "rubin") return false;
  return e.observed_at >= rubinWindow.start && e.observed_at < rubinWindow.end;
}

function normalise(e, pics) {
  const raw = smallRaw(e.raw);
  if (rubinLatest(e)) raw.from_latest_observed_window = true;
  return {
    id: e.id,
    type: e.type,
    title: e.title,
    summary: e.summary,
    // The contract's id is "<source>:<source's own id>"; the example fixture has display names in
    // `source` ("JPL Horizons"), so take the key from the id.
    source: e.id.split(":")[0],
    source_url: e.source_url,
    observed_at: e.observed_at,
    reported_at: e.reported_at,
    location: e.location,
    confidence: e.confidence,
    confidence_basis: basis(e),
    brightness_mag: e.brightness_mag,
    images: (pics ?? e.images ?? []).map(image),
    raw,
  };
}

const chosen = new Map();
// 1. Every example, preferring the contract-exact record from the week run when it is there.
for (const ex of examples) {
  const e = byId.get(ex.id) ?? ex;
  chosen.set(ex.id, normalise({ ...e, source: e.source ?? ex.source }, pictures[ex.id]));
}

// 2. A spread of the real week: per (source, type), newest first, up to a quota.
const quota = {
  "donki:coronal_mass_ejection": 5,
  "donki:solar_flare": 1,
  "gcn:gamma_ray_burst": 5,
  "mpc:near_earth_object": 7,
  "mpc:comet": 2,
  "jpl:comet": 1,
  "ztf:supernova": 5,
  "ztf:active_galaxy_flare": 2,
  "ztf:variable_star": 2,
  "ztf:unknown": 1,
  "tns:supernova": 5,
  "icecube:neutrino": 1,
  "rubin:supernova": 3,
  "rubin:active_galaxy_flare": 2,
  "rubin:variable_star": 2,
  "rubin:unknown": 1,
};
const sorted = [...week].sort((a, b) => b.observed_at.localeCompare(a.observed_at));
for (const e of sorted) {
  const key = `${e.source}:${e.type}`;
  if (!quota[key] || chosen.has(e.id)) continue;
  quota[key]--;
  chosen.set(e.id, normalise(e));
}

const events = [...chosen.values()].sort((a, b) => b.observed_at.localeCompare(a.observed_at));
const meta = {
  demo: true,
  note: "DEMO DATA: real events recorded 2026-09-18 to 2026-09-25 and the PICTURES examples, served from a static file.",
  recorded_until: status.window?.until ?? status.generated_at,
};
await writeFile(path.join(out, "events.mock.json"), JSON.stringify({ meta, events }));

// SourceStatus list, from status.json's sources map.
const sources = Object.entries(status.sources).map(([source, s]) => ({
  source,
  is_live: !!s.live,
  state: s.state,
  last_event_at: s.last_event_at ?? null,
  checked_at: status.generated_at,
  events: s.events ?? 0,
  note: s.note ?? null,
  error: s.error ?? null,
}));
await writeFile(path.join(out, "status.mock.json"), JSON.stringify({ generated_at: status.generated_at, sources }));

const count = (f) => events.reduce((m, e) => ((m[f(e)] = (m[f(e)] ?? 0) + 1), m), {});
console.log(`${events.length} events`, count((e) => e.type));
console.log(count((e) => e.location.frame), "with pictures:", events.filter((e) => e.images.length).length);

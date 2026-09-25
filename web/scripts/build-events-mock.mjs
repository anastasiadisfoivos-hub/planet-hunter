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

// The PICTURES example fixture set observed_at for its three JPL objects to the Horizons position
// epoch it asked for (2026-09-25T16:00Z): that is when the position was computed, not an observation,
// and it made them read "3 min ago". The events service uses the last observation (SBDB orbit
// last_obs, see the week run's jpl records). These are SBDB's answers, queried 2026-09-25
// (https://ssd-api.jpl.nasa.gov/sbdb.api?sstr=...), pinned here so the build stays offline.
const JPL_LAST_OBS = {
  "jpl:2026 SA8": "2026-09-22T00:00:00Z", // (2026 SA8): first 2026-09-20, last 2026-09-22
  "jpl:29P/Schwassmann-Wachmann": "2025-02-05T00:00:00Z", // 29P/Schwassmann-Wachmann 1: last 2025-02-05
  "jpl:3I/ATLAS": "2026-02-19T00:00:00Z", // C/2025 N1 (ATLAS): last 2026-02-19
};

/**
 * Times, per the events contract: observed_at is when the thing was observed. When a source gives no
 * report time, the service sets reported_at = observed_at and raw.reported_at_known = false (events
 * README). Some TNS records came through with an older reported_at than observed_at; normalise those.
 */
// Sources that publish no report time (events README): the service flags them reported_at_known = false.
// The example fixture stamped its own run time as reported_at instead (the CNEOS fireball read "just now").
const NO_REPORT_TIME = new Set(["cneos", "tns", "jpl"]);

function fixTimes(e, raw) {
  let observed = e.observed_at;
  if (NO_REPORT_TIME.has(e.id.split(":")[0])) raw.reported_at_known = false;
  if (JPL_LAST_OBS[e.id]) {
    raw.position_epoch = e.observed_at;
    observed = JPL_LAST_OBS[e.id];
    raw.reported_at_known = false;
  }
  // A report time after the recording ended is the example fixture's own run time, not a report.
  if (e.reported_at > (status.window?.until ?? status.generated_at)) raw.reported_at_known = false;
  let reported = raw.reported_at_known === false ? observed : e.reported_at;
  if (reported < observed) {
    raw.reported_at_known = false;
    reported = observed;
  }
  return { observed_at: observed, reported_at: reported };
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
  const times = fixTimes(e, raw);
  return {
    id: e.id,
    type: e.type,
    title: e.title,
    summary: e.summary,
    // The contract's id is "<source>:<source's own id>"; the example fixture has display names in
    // `source` ("JPL Horizons"), so take the key from the id.
    source: e.id.split(":")[0],
    source_url: e.source_url,
    observed_at: times.observed_at,
    reported_at: times.reported_at,
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

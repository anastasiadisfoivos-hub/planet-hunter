// Typed client for the events API. Owned by the SPOTMAP session.
//
// MOCK mode is ON by default: it serves web/public/data/events.mock.json and status.mock.json, which
// hold REAL recorded events and source status (built by scripts/build-events-mock.mjs). The whole mock
// is shown as DEMO DATA, and its clock is pinned to the end of the recording, so "last 7 days" means
// the recorded week. For a real server, set NEXT_PUBLIC_API_MOCK=false and NEXT_PUBLIC_API_BASE.
//
// Shapes (SkyEvent, SourceStatus) come from the shared event contract. The query-string names below
// follow skyevents.query's filter keys; they are this client's working assumption until the api
// session publishes its HTTP routes.

import type { SkyEvent, SourceStatus } from "@/lib/contract";
import { applyFilters, page, timeWindow, type EventFilters } from "@/lib/events";

export const API_MOCK = process.env.NEXT_PUBLIC_API_MOCK !== "false";
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

export type EventsPage = { events: SkyEvent[]; total: number; next: string | null };
export type Status = { generated_at: string; sources: SourceStatus[] };

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

type MockFile = { meta: { demo: true; note: string; recorded_until: string }; events: SkyEvent[] };
let mock: Promise<MockFile> | null = null;

async function getJson<T>(url: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new ApiError(res.status, `${url}: ${res.status}`);
  return res.json() as Promise<T>;
}

function mockData(): Promise<MockFile> {
  mock ??= getJson<MockFile>("/data/events.mock.json");
  return mock;
}

/** "Now" for relative times and time ranges: the recording's end in mock mode, the real clock otherwise. */
export async function clockNow(): Promise<number> {
  return API_MOCK ? Date.parse((await mockData()).meta.recorded_until) : Date.now();
}

/** Every event the filters could ever match, for the map and the counts (mock: the whole file). */
export async function getAllEvents(signal?: AbortSignal): Promise<SkyEvent[]> {
  if (API_MOCK) return (await mockData()).events;
  const all: SkyEvent[] = [];
  let cursor: string | null = null;
  do {
    const p: EventsPage = await getJson<EventsPage>(`${API_BASE}/events?limit=500${cursor ? `&cursor=${cursor}` : ""}`, signal);
    all.push(...p.events);
    cursor = p.next;
  } while (cursor);
  return all;
}

/** One page of events matching the filters, newest first. */
export async function getEvents(filters: EventFilters, opts: { cursor?: string | null; limit?: number; signal?: AbortSignal } = {}): Promise<EventsPage> {
  const limit = opts.limit ?? 30;
  if (API_MOCK) {
    const now = await clockNow();
    const all = applyFilters((await mockData()).events, filters, now);
    const p = page(all, opts.cursor ?? null, limit);
    return { events: p.items, total: all.length, next: p.next };
  }
  const [since, until] = timeWindow(filters.time, Date.now());
  const q = new URLSearchParams({
    since: new Date(since).toISOString(),
    until: new Date(until).toISOString(),
    types: filters.types.join(","),
    min_confidence: String(filters.minConfidence),
    limit: String(limit),
  });
  if (filters.sources.length) q.set("sources", filters.sources.join(","));
  if (filters.withPictures) q.set("with_images", "true");
  if (filters.rubinLatest) q.set("include_latest_observed_window", "true");
  if (opts.cursor) q.set("cursor", opts.cursor);
  return getJson<EventsPage>(`${API_BASE}/events?${q}`, opts.signal);
}

export async function getEvent(id: string, signal?: AbortSignal): Promise<SkyEvent> {
  if (API_MOCK) {
    const e = (await mockData()).events.find((x) => x.id === id);
    if (!e) throw new ApiError(404, `No event ${id}`);
    return e;
  }
  return getJson<SkyEvent>(`${API_BASE}/events/${encodeURIComponent(id)}`, signal);
}

export async function getStatus(signal?: AbortSignal): Promise<Status> {
  return getJson<Status>(API_MOCK ? "/data/status.mock.json" : `${API_BASE}/status`, signal);
}

// ---------- Analyze a star (TESS light-curve search) ----------
//
// The pipeline (hunter.core.run) runs four steps: resolve, fetch, search, vet_known_flares. MOCK mode
// replays them as a fake job and returns the pipeline's stored real result for WASP-18
// (pipeline/reports/wasp-18), marked as a demo for any other star. The real endpoints come from the
// SPOTAPI session; the shapes below are this client's working assumption until then.

export type AnalyzeTarget = { name: string; tic_id?: number; hip?: number; ra_deg: number; dec_deg: number };

export type StepKey = "resolve" | "fetch" | "search" | "vet_known_flares";
export type JobStep = { key: StepKey; label: string; state: "pending" | "running" | "done"; seconds: number | null };

/** The pipeline's result.json shape (hunter), as far as the UI reads it. */
export type AnalysisResult = {
  target: { tic_id: number; query: string; ra_deg: number; dec_deg: number; stellar_radius_rsun: number; teff_k: number; tmag: number };
  data: { sector: number; author: string; exptime: number }[];
  discoveries: {
    id: string;
    type: string;
    confidence: number;
    name_if_known: string | null;
    known_status: string;
    explanation: string;
    links: { label: string; url: string }[];
  }[];
  flares_found: number;
  timings_s: Record<string, number>;
  plots: string[];
};

export type AnalyzeJob = {
  id: string;
  target: AnalyzeTarget;
  status: "queued" | "running" | "done" | "failed";
  steps: JobStep[];
  result: AnalysisResult | null;
  /** Base URL for the result's plot files. */
  plotBase: string | null;
  /** True when the result is the stored WASP-18 demo rather than this star's own analysis. */
  demo: boolean;
};

export const STEPS: { key: StepKey; label: string; mockSeconds: number }[] = [
  { key: "resolve", label: "Find the star in the TESS Input Catalog", mockSeconds: 0.8 },
  { key: "fetch", label: "Download TESS light curves", mockSeconds: 1.8 },
  { key: "search", label: "Search for repeating dips", mockSeconds: 2.3 }, // WASP-18's real search took 2.29 s
  { key: "vet_known_flares", label: "Check signals, known planets and flares", mockSeconds: 0.7 },
];

const mockJobs = new Map<string, { target: AnalyzeTarget; start: number }>();
let demoResult: Promise<AnalysisResult> | null = null;

export async function analyze(target: AnalyzeTarget): Promise<{ job_id: string }> {
  if (API_MOCK) {
    const job_id = `mock-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
    mockJobs.set(job_id, { target, start: Date.now() });
    return { job_id };
  }
  // STARDATA reads `tic_id` at the top level; `target` stays for the older SPOTAPI shape.
  const res = await fetch(`${API_BASE}/analyze`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ tic_id: target.tic_id, target }),
  });
  if (!res.ok) throw new ApiError(res.status, `analyze: ${res.status}`);
  return res.json();
}

export async function getJob(id: string, signal?: AbortSignal): Promise<AnalyzeJob> {
  if (!API_MOCK) return getJson<AnalyzeJob>(`${API_BASE}/jobs/${encodeURIComponent(id)}`, signal);
  const j = mockJobs.get(id);
  if (!j) throw new ApiError(404, `No job ${id}`);
  const elapsed = (Date.now() - j.start) / 1000;
  let t = 0;
  const steps: JobStep[] = STEPS.map((s) => {
    const begin = t;
    t += s.mockSeconds;
    const state = elapsed >= t ? "done" : elapsed >= begin ? "running" : "pending";
    return { key: s.key, label: s.label, state, seconds: state === "done" ? s.mockSeconds : null };
  });
  const done = elapsed >= t;
  if (done && j.target.tic_id) mockAnalyzed.add(j.target.tic_id);
  demoResult ??= getJson<AnalysisResult>("/data/analysis/wasp-18/result.json");
  const isWasp18 = j.target.tic_id === 100100827 || /^WASP-18$/i.test(j.target.name);
  return {
    id,
    target: j.target,
    status: done ? "done" : "running",
    steps,
    result: done ? await demoResult : null,
    plotBase: done ? "/data/analysis/wasp-18/" : null,
    demo: !isWasp18,
  };
}

// ---------- A star's own lab (GET /stars/{tic}/lab, GET /stars/{tic}/lightcurve) ----------
//
// Served by the STARDATA session. Until it is live, MOCK mode builds the same shapes from
// public/data/hosts.json and public/data/lab/star-lab.mock.json (real NASA Exoplanet Archive values),
// with two stored real TESS analyses (WASP-18, WASP-121). Which stars have a light curve is a stand-in
// rule: Tmag brighter than 4 is "too_bright", no TESS magnitude is "no_tess_data", and the rest are
// "not_analyzed" until the mock job above has run for them.

export type LabSignal = { period_d: number; t0: number; duration_h: number; depth_ppm: number };
/** radius in Earth radii, mass in Earth masses (the archive's pl_rade and pl_bmasse). */
export type KnownPlanet = { name: string; period_d: number | null; a_au: number | null; radius: number | null; mass: number | null };
export type LightcurveReason = "not_analyzed" | "no_tess_data" | "too_bright";

export type StarLab = {
  tic: number;
  name: string;
  /** Kelvin; radius in Suns; distance in parsecs; tmag in TESS magnitudes. */
  teff: number | null;
  radius: number | null;
  distance: number | null;
  tmag: number | null;
  /** Star mass in Suns. Not in the STARDATA shape yet (requested); the Lab estimates it when missing. */
  mass?: number | null;
  lightcurve: { available: boolean; reason_if_not: LightcurveReason | string | null };
  signals: LabSignal[];
  known_planets: KnownPlanet[];
  /** gaia_xp and abundances: whether the SPECTRA files exist for this star. */
  spectra: { gaia_xp: boolean; abundances: boolean; planet_atmospheres: string[] };
};

export type StarLightcurve = { unfolded: { time_btjd: number[]; flux: number[] }; folded: { phase: number[]; flux: number[] } };

/** A lab response plus what in it is a stand-in. `standIn` names the star whose data is borrowed. */
export type Served<T> = { data: T; demo: boolean; standIn: string | null };

type StoredResult = {
  target: { query: string };
  discoveries: { light_curve: { time_btjd: number[]; flux: number[] }; raw: { signal: { period: number; t0: number; duration: number; depth: number } } }[];
};
type StarLabMock = { meta: { source: string }; stars: Record<string, { mass: number | null; tmag: number | null; planets: [string, number | null, number | null, number | null, number | null][] }> };

/** Real TESS analyses kept in the repo, by TIC. */
const STORED: Record<number, string> = { 100100827: "wasp-18", 22529346: "wasp-121" };
const STAND_IN_TIC = 100100827;
/** Stars with SPECTRA stand-in files (public/data/lab/spectra-mock). */
const MOCK_SPECTRA = new Set([100100827, 22529346, 181949561]);
const MOCK_ATMOSPHERES = ["wasp-121-b", "wasp-39-b", "wasp-18-b"];
export const TOO_BRIGHT_TMAG = 4;

const mockAnalyzed = {
  key: "ph-lab-analyzed",
  read(): number[] {
    try {
      return JSON.parse(sessionStorage.getItem(this.key) ?? "[]") as number[];
    } catch {
      return [];
    }
  },
  has(tic: number) {
    return this.read().includes(tic);
  },
  add(tic: number) {
    try {
      sessionStorage.setItem(this.key, JSON.stringify([...new Set([...this.read(), tic])]));
    } catch {
      /* private mode: the unlock lasts until reload */
    }
    mockAnalyzedMemory.add(tic);
  },
};
const mockAnalyzedMemory = new Set<number>();

let hostsMock: Promise<import("@/lib/data").HostsFile> | null = null;
let starLabMock: Promise<StarLabMock> | null = null;
const stored = new Map<number, Promise<StoredResult>>();
const storedResult = (tic: number) => {
  if (!stored.has(tic)) stored.set(tic, getJson<StoredResult>(`/data/lab/${STORED[tic]}.result.json`));
  return stored.get(tic)!;
};

function signalsOf(r: StoredResult): LabSignal[] {
  return r.discoveries.map(({ raw: { signal: g } }) => ({ period_d: g.period, t0: g.t0, duration_h: g.duration * 24, depth_ppm: g.depth * 1e6 }));
}

export async function getStarLab(tic: number, signal?: AbortSignal): Promise<Served<StarLab>> {
  if (!API_MOCK) return { data: await getJson<StarLab>(`${API_BASE}/stars/${tic}/lab`, signal), demo: false, standIn: null };
  hostsMock ??= getJson("/data/hosts.json");
  starLabMock ??= getJson("/data/lab/star-lab.mock.json");
  const [hosts, extra] = await Promise.all([hostsMock, starLabMock]);
  const i = hosts.tic.indexOf(tic);
  if (i < 0) throw new ApiError(404, `TIC ${tic} is not one of the map's planet hosts`);
  const x = extra.stars[tic] ?? { mass: null, tmag: null, planets: [] };
  const own = tic in STORED;
  const analyzed = own || mockAnalyzed.has(tic) || mockAnalyzedMemory.has(tic);
  const reason: LightcurveReason | null =
    x.tmag != null && x.tmag < TOO_BRIGHT_TMAG ? "too_bright" : x.tmag == null ? "no_tess_data" : analyzed ? null : "not_analyzed";
  const standIn = !reason && !own;
  const signals = reason ? [] : signalsOf(await storedResult(own ? tic : STAND_IN_TIC));
  const known_planets = x.planets.map(([name, period_d, a_au, radius, mass]) => ({ name, period_d, a_au, radius, mass }));
  const slug = (n: string) => n.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
  return {
    data: {
      tic,
      name: hosts.name[i],
      teff: hosts.teff[i] > 0 ? hosts.teff[i] : null,
      radius: hosts.rad?.[i] > 0 ? hosts.rad[i] : null,
      distance: hosts.dist[i] > 0 ? hosts.dist[i] : null,
      tmag: x.tmag,
      mass: x.mass,
      lightcurve: { available: !reason, reason_if_not: reason },
      signals,
      known_planets,
      spectra: {
        gaia_xp: MOCK_SPECTRA.has(tic),
        abundances: MOCK_SPECTRA.has(tic),
        planet_atmospheres: known_planets.map((p) => slug(p.name)).filter((sl) => MOCK_ATMOSPHERES.includes(sl)),
      },
    },
    demo: true,
    standIn: standIn ? "WASP-18" : null,
  };
}

export async function getStarLightcurve(tic: number, signal?: AbortSignal): Promise<Served<StarLightcurve>> {
  if (!API_MOCK) return { data: await getJson<StarLightcurve>(`${API_BASE}/stars/${tic}/lightcurve`, signal), demo: false, standIn: null };
  const own = tic in STORED;
  const r = await storedResult(own ? tic : STAND_IN_TIC);
  const d = r.discoveries[0];
  const { period, t0 } = d.raw.signal;
  const { time_btjd, flux } = d.light_curve;
  const phase = time_btjd.map((t) => {
    const p = ((((t - t0) / period) % 1) + 1) % 1;
    return p >= 0.5 ? p - 1 : p;
  });
  const order = phase.map((_, k) => k).sort((a, b) => phase[a] - phase[b]);
  return {
    data: { unfolded: { time_btjd, flux }, folded: { phase: order.map((k) => phase[k]), flux: order.map((k) => flux[k]) } },
    demo: true,
    standIn: own ? null : r.target.query,
  };
}

// ---------- Monitor and candidates: the planet finder ----------
//
// Routes (the FINDER API): GET /monitor/now, /monitor/log, /monitor/coverage, /monitor/stats, and the /finder/*
// routes for candidates, votes and sensitivity. None is live yet, so MOCK mode serves public/data/monitor/*,
// built by components/monitor/data/build_monitor_data.py from REAL data only: TESS light curves (hunt's test
// fixtures and stars from the 2026-09-26 sweep), hunt's own search of each, the sweep's log, Gaia DR3 and VSX.
// The sweep found no new candidate, so the mock's candidates are real TESS Objects of Interest shown as
// stand-ins, each saying so (Candidate.stand_in). Mock mode is always a replay, never "live".

export type DetectionKind = "periodic" | "duo" | "single";
export type DetectionOutcome = "candidate" | "rejected" | "known";

/** A dip the search found in a star's light curve. Times are BTJD (BJD - 2457000). */
export type Detection = {
  t0: number;
  duration_h: number;
  depth_ppm: number | null;
  period_d: number | null;
  kind: DetectionKind;
  outcome: DetectionOutcome;
  /** Why it was kept or turned down, in words. */
  reason: string;
};

export type StarOutcome = DetectionOutcome | "none";

/** A star the search looked at: its catalogue facts, its data, and what the search found. */
export type MonitorStar = {
  tic: number;
  tmag: number | null;
  teff: number | null;
  radius_rsun: number | null;
  ra: number;
  dec: number;
  sectors: number[];
  /** First and last TESS observation used (ISO, UTC). */
  observed_from: string | null;
  observed_to: string | null;
  /** Normalised flux against BTJD; null in the log. */
  lightcurve: { t: number[]; f: number[] } | null;
  detections: Detection[];
  outcome: StarOutcome;
  searched_at: string;
};

export type MonitorMode = "live" | "replay";

export type MonitorNow = {
  mode: MonitorMode;
  star: MonitorStar;
  /** Replay only: when the search being replayed ran (ISO). */
  replay_of: string | null;
  /** The star that comes after this one, so the client can fetch it early. */
  next_tic: number | null;
};

export type LogStar = Omit<MonitorStar, "lightcurve">;
export type MonitorLog = { stars: LogStar[] };
export type CoverageStar = { tic: number; ra: number; dec: number; outcome: StarOutcome; sectors: number[] };
export type MonitorCoverage = { stars: CoverageStar[] };
export type MonitorStats = {
  since: string;
  updated_at: string;
  stars_searched: number;
  signals: number;
  candidates: number;
  rejected: number;
  known: number;
};

const MON = "/data/monitor";
type ReplayFile = { built_at: string; order: number[] };
let replayFile: Promise<ReplayFile> | null = null;
const replay = () => (replayFile ??= getJson<ReplayFile>(`${MON}/replay.json`));

/** The date the mock replays: the day of the recorded sweep. */
export const MOCK_REPLAY_OF = "2026-09-26T07:57:39Z";

/**
 * The star being searched now (live), or the next star of a replay. `after` asks for the star after that TIC,
 * which is how a replay advances; a live server ignores it and answers with whatever it is searching.
 */
export async function getMonitorNow(opts: { after?: number | null; signal?: AbortSignal } = {}): Promise<MonitorNow> {
  if (!API_MOCK) {
    const q = opts.after != null ? `?after=${opts.after}` : "";
    return getJson<MonitorNow>(`${API_BASE}/monitor/now${q}`, opts.signal);
  }
  const { order } = await replay();
  const i = opts.after == null ? 0 : (order.indexOf(opts.after) + 1) % order.length;
  const star = await getJson<MonitorStar>(`${MON}/stars/${order[i]}.json`, opts.signal);
  return { mode: "replay", star, replay_of: MOCK_REPLAY_OF, next_tic: order[(i + 1) % order.length] };
}

export async function getMonitorLog(signal?: AbortSignal): Promise<MonitorLog> {
  return getJson<MonitorLog>(API_MOCK ? `${MON}/log.json` : `${API_BASE}/monitor/log`, signal);
}

export async function getMonitorCoverage(signal?: AbortSignal): Promise<MonitorCoverage> {
  return getJson<MonitorCoverage>(API_MOCK ? `${MON}/coverage.json` : `${API_BASE}/monitor/coverage`, signal);
}

export async function getMonitorStats(signal?: AbortSignal): Promise<MonitorStats> {
  return getJson<MonitorStats>(API_MOCK ? `${MON}/stats.json` : `${API_BASE}/monitor/stats`, signal);
}

/** A searched star's light curve, when the mock has it (the log itself carries none). */
export async function getStarCurve(tic: number, signal?: AbortSignal): Promise<MonitorStar | null> {
  if (!API_MOCK) return null;
  if (!(await replay()).order.includes(tic)) return null;
  return getJson<MonitorStar>(`${MON}/stars/${tic}.json`, signal).catch(() => null);
}

export type CheckResult = { name: string; value: number | string | null; passed: boolean | null; reason: string };

/** One list a signal is compared against. `true` or `{ matched: true }` means it is already known. */
export type KnownListResult = boolean | { matched: boolean; id?: string | null };
export type KnownLists = { confirmed: KnownListResult; toi: KnownListResult; ctoi: KnownListResult; eb: KnownListResult };

export type Candidate = {
  id: string;
  tic: number;
  name?: string | null;
  period_d: number;
  t0_btjd: number;
  duration_h: number;
  depth_ppm: number;
  snr: number;
  sde: number;
  n_transits: number;
  sectors: number[];
  /** Best radius and its likely range, in Jupiter radii. */
  radius_rjup: number;
  radius_low: number;
  radius_high: number;
  checks: CheckResult[];
  /** 0 to 1: a machine ranking, the sum of score_parts. */
  score: number;
  score_parts: Record<string, number>;
  known_lists: KnownLists;
  folded: { phase: number[]; flux: number[] };
  unfolded: { time_btjd: number[]; flux: number[] };
  created_at: string;
  /** Mock only: a real TESS Object of Interest shown in place of a new candidate, and why. */
  stand_in?: StandIn | null;
  /** A finer fold around the dip (hunt: 60 bins over three durations either side), when the API sends it. */
  folded_zoom?: { hours_from_mid: number[]; flux: number[] } | null;
  /** Candidate detail only: the vetting block (FINDER API). */
  vetting?: Vetting;
  /** The TIC row of the host star, when the API sends it. */
  star?: { tmag: number | null; teff: number | null; rad: number | null; ra: number; dec: number } | null;
};

export type StandIn = { name: string; disposition: string | null; note: string };

export type Vetting = {
  leo: { ran: boolean; passed: boolean | null; flags: string[] };
  triceratops: { ran: boolean; fpp: number | null; nfpp: number | null };
  gaia: {
    ruwe: number | null;
    neighbours: { gaia_id: string; sep_arcsec: number; gmag: number; can_mimic?: boolean; needed_depth?: number }[];
    binary_hint: boolean;
    gaia_id?: string | null;
  };
  variability: { vsx_match: { name: string; type: string; sep_arcsec: number; period_d: number | null } | null; gaia_variable: boolean };
  summary: { verdict: string; reasons: string[] };
};

export type PixelVerdict = "on target" | "possible neighbour" | "off target" | "inconclusive";

/** A star drawn on the pixel images, in pixel coordinates (pixel centres at integers, x = column, y = row). */
export type PixelMarker = { kind: "target" | "neighbour" | "suspect"; gaia_id: string | null; x: number; y: number; gmag?: number; needed_depth?: number | null; label?: string };

export type PixelVet = {
  verdict: PixelVerdict;
  reason: string;
  on_target_probability: number | null;
  centroid_offset_arcsec: number | null;
  offset_sigma: number | null;
  suspect_neighbours: { gaia_id: string; sep_arcsec: number; gmag: number; needed_depth: number }[];
  images: {
    /** image[row][col] in e-/s. */
    out_of_transit: number[][];
    /** Out-of-transit minus in-transit: positive where light was lost during the dip. */
    difference: number[][];
    markers: PixelMarker[];
    centroid?: { x: number; y: number } | null;
    sector?: number;
    pixel_scale_arcsec?: number;
    /** Unit vectors in pixel (x, y) pointing north and east. */
    compass?: { north: [number, number]; east: [number, number] };
    /** Demo only: the real PIXELS run these images were copied from. */
    borrowed_from?: string;
  };
};

export type VoteChoice = "planet" | "fake" | "unsure";
export type Votes = { planet: number; fake: number; unsure: number; my_vote: VoteChoice | null; my_reasons?: string[] };

export type Sensitivity = {
  run_at: string;
  stars_used: number;
  radius_edges_rearth: number[];
  period_edges_d: number[];
  /** recovery_pct[radius bin][period bin], 0 to 100; null where nothing was injected. */
  recovery_pct: (number | null)[][];
  n_injected: number[][];
  /** What "detected" and "recovered" mean, in words (hunt's sensitivity run). */
  definition?: Record<string, string>;
  overall_recovery_pct?: number;
};

export type FunnelStep = { key: string; label: string; count: number };

/** A row in the candidate list: the Candidate without its curves and checks, plus its pixel verdict and votes. */
export type CandidateRow = Omit<Candidate, "folded" | "unfolded" | "checks" | "vetting"> & {
  checks_passed: number;
  checks_total: number;
  pixel_verdict: PixelVerdict | null;
  votes: Votes;
  /** The vetting summary's verdict, when vetting has run. */
  verdict?: string | null;
};

export type CandidateList = { run_at: string; funnel: FunnelStep[]; candidates: CandidateRow[]; demo: boolean };
export type CandidateReport = { candidate: Candidate; pixels: PixelVet | null; votes: Votes; demo: boolean };


type CandidateIndexMock = { run_at: string; candidates: CandidateRow[] };
let candIndex: Promise<CandidateIndexMock> | null = null;
const candMockIndex = () => (candIndex ??= getJson<CandidateIndexMock>(`${MON}/candidates/index.json`));
type StatsMock = MonitorStats & { sweep_2026_09_26?: Record<string, number | Record<string, number> | string[]> };

/** The search's funnel, from the recorded sweep's own counts. */
async function mockFunnel(): Promise<FunnelStep[]> {
  const s = await getJson<StatsMock>(`${MON}/stats.json`);
  const f = (s.sweep_2026_09_26 ?? {}) as Record<string, number>;
  return [
    { key: "stars", label: "Stars searched", count: f.stars_searched ?? s.stars_searched },
    { key: "signals", label: "Repeating dips found", count: f.signals_found ?? s.signals },
    { key: "snr", label: "Strong enough", count: f.after_snr ?? 0 },
    { key: "sde", label: "Stand out from other periods", count: f.after_sde ?? 0 },
    { key: "checks", label: "Passed the checks", count: f.after_checks ?? 0 },
    { key: "candidates", label: "New candidates", count: f.candidates ?? s.candidates },
  ];
}

/** Demo votes: this browser's own vote, kept per candidate on top of the mock's counts. */
const myVotes = {
  key: "ph-finder-votes",
  read(): Record<string, { vote: VoteChoice; reasons: string[] }> {
    try {
      return JSON.parse(localStorage.getItem(this.key) ?? "{}");
    } catch {
      return {};
    }
  },
  write(id: string, v: { vote: VoteChoice; reasons: string[] } | null) {
    const all = this.read();
    if (v) all[id] = v;
    else delete all[id];
    try {
      localStorage.setItem(this.key, JSON.stringify(all));
    } catch {
      /* private mode: the vote lasts until reload */
    }
  },
};

function withMyVote(id: string, base: Votes): Votes {
  const mine = myVotes.read()[id];
  if (!mine) return { ...base, my_vote: null, my_reasons: [] };
  return { ...base, [mine.vote]: base[mine.vote] + 1, my_vote: mine.vote, my_reasons: mine.reasons };
}

export async function getCandidates(signal?: AbortSignal): Promise<CandidateList> {
  if (!API_MOCK) return { ...(await getJson<Omit<CandidateList, "demo">>(`${API_BASE}/finder/candidates`, signal)), demo: false };
  const [ix, funnel] = await Promise.all([candMockIndex(), mockFunnel()]);
  return { run_at: ix.run_at, funnel, candidates: ix.candidates.map((c) => ({ ...c, votes: withMyVote(c.id, c.votes) })), demo: true };
}

export async function getCandidate(id: string, signal?: AbortSignal): Promise<CandidateReport> {
  if (!API_MOCK) return { ...(await getJson<Omit<CandidateReport, "demo">>(`${API_BASE}/finder/candidates/${encodeURIComponent(id)}`, signal)), demo: false };
  if (!/^[a-z0-9-]+$/i.test(id)) throw new ApiError(404, `No candidate ${id}`);
  const r = await getJson<Omit<CandidateReport, "demo">>(`${MON}/candidates/${id}.json`, signal).catch((e: unknown) => {
    throw e instanceof ApiError && e.status === 404 ? new ApiError(404, `No candidate ${id}`) : e;
  });
  return { ...r, votes: withMyVote(id, r.votes), demo: true };
}

/** Cast, change (`vote` set) or take back (`vote` null) this viewer's vote. Returns the new totals. */
export async function submitVote(id: string, vote: VoteChoice | null, reasons: string[]): Promise<Votes> {
  if (!API_MOCK) {
    const res = await fetch(`${API_BASE}/finder/candidates/${encodeURIComponent(id)}/vote`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ vote, reasons }),
    });
    if (!res.ok) throw new ApiError(res.status, `vote: ${res.status}`);
    return res.json();
  }
  const base = (await candMockIndex()).candidates.find((c) => c.id === id)?.votes;
  if (!base) throw new ApiError(404, `No candidate ${id}`);
  await new Promise((ok) => setTimeout(ok, 250));
  myVotes.write(id, vote ? { vote, reasons } : null);
  return withMyVote(id, base);
}

export async function getSensitivity(signal?: AbortSignal): Promise<Served<Sensitivity>> {
  if (!API_MOCK) return { data: await getJson<Sensitivity>(`${API_BASE}/finder/sensitivity`, signal), demo: false, standIn: null };
  return { data: await getJson<Sensitivity>(`${MON}/sensitivity.json`, signal), demo: true, standIn: null };
}

/** Admin: the selected candidates as an ExoFOP CTOI upload file. The API checks the token; the demo builds it here and sends nothing. */
export async function exportCtoiCsv(ids: string[], token: string): Promise<{ filename: string; csv: string }> {
  if (!API_MOCK) {
    const res = await fetch(`${API_BASE}/finder/export/ctoi`, {
      method: "POST",
      headers: { "content-type": "application/json", authorization: `Bearer ${token}` },
      body: JSON.stringify({ ids }),
    });
    if (!res.ok) throw new ApiError(res.status, res.status === 401 || res.status === 403 ? "The admin token was not accepted." : `export: ${res.status}`);
    return { filename: `ctoi-${new Date().toISOString().slice(0, 10)}.csv`, csv: await res.text() };
  }
  const reports = await Promise.all(ids.map((id) => getCandidate(id)));
  const { ctoiCsv } = await import("@/components/finder/finder");
  return { filename: "ctoi-demo.csv", csv: ctoiCsv(reports.map((r) => r.candidate)) };
}

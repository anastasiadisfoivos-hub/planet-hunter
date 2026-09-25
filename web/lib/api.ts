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

// ---------- Finder: planet candidates from the nightly search ----------
//
// Candidate comes from the HUNT session, PixelVet from the PIXELS session; votes and the injection-recovery
// grid from the FINDER API. None of those routes is live yet, so MOCK mode serves public/data/finder/*
// (built by components/finder/data/build-finder-mock.mjs): made-up candidates with simulated light curves,
// and pixel images borrowed from two real PIXELS runs. The route names below are this client's working
// assumption until the FINDER API publishes its own.

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
  /** recovery_pct[radius bin][period bin], 0 to 100. */
  recovery_pct: number[][];
  n_injected: number[][];
};

export type FunnelStep = { key: string; label: string; count: number };

/** A row in the candidate list: the Candidate without its curves and checks, plus its pixel verdict and votes. */
export type CandidateRow = Omit<Candidate, "folded" | "unfolded" | "checks"> & {
  checks_passed: number;
  checks_total: number;
  pixel_verdict: PixelVerdict | null;
  votes: Votes;
};

export type CandidateList = { run_at: string; funnel: FunnelStep[]; candidates: CandidateRow[]; demo: boolean };
export type CandidateReport = { candidate: Candidate; pixels: PixelVet | null; votes: Votes; demo: boolean };

type FinderIndexMock = { meta: { run_at: string; funnel: FunnelStep[] }; candidates: CandidateRow[] };
let finderIndex: Promise<FinderIndexMock> | null = null;
const finderMockIndex = () => (finderIndex ??= getJson<FinderIndexMock>("/data/finder/index.mock.json"));

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
  const ix = await finderMockIndex();
  return { run_at: ix.meta.run_at, funnel: ix.meta.funnel, candidates: ix.candidates.map((c) => ({ ...c, votes: withMyVote(c.id, c.votes) })), demo: true };
}

export async function getCandidate(id: string, signal?: AbortSignal): Promise<CandidateReport> {
  if (!API_MOCK) return { ...(await getJson<Omit<CandidateReport, "demo">>(`${API_BASE}/finder/candidates/${encodeURIComponent(id)}`, signal)), demo: false };
  if (!/^[a-z0-9-]+$/i.test(id)) throw new ApiError(404, `No candidate ${id}`);
  const r = await getJson<Omit<CandidateReport, "demo">>(`/data/finder/c/${id}.json`, signal).catch((e: unknown) => {
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
  const base = (await finderMockIndex()).candidates.find((c) => c.id === id)?.votes;
  if (!base) throw new ApiError(404, `No candidate ${id}`);
  await new Promise((ok) => setTimeout(ok, 250));
  myVotes.write(id, vote ? { vote, reasons } : null);
  return withMyVote(id, base);
}

export async function getSensitivity(signal?: AbortSignal): Promise<Served<Sensitivity>> {
  if (!API_MOCK) return { data: await getJson<Sensitivity>(`${API_BASE}/finder/sensitivity`, signal), demo: false, standIn: null };
  return { data: await getJson<Sensitivity>("/data/finder/sensitivity.mock.json", signal), demo: true, standIn: null };
}

/** Which TICs are planet hosts on the sky map, so their candidates can link to a star lab and a flight. */
let hostTics: Promise<Set<number>> | null = null;
export function getMapHostTics(): Promise<Set<number>> {
  hostTics ??= getJson<{ tic: number[] }>("/data/hosts.json").then((h) => new Set(h.tic));
  return hostTics;
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

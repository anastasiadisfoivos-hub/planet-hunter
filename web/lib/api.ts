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
  const res = await fetch(`${API_BASE}/analyze`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ target }) });
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

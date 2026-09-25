// Typed client for the TRAPS API. Owned by the SKYMAP session.
//
// MOCK mode is ON by default and answers every call locally with contract-shaped data. To use a real
// server, set NEXT_PUBLIC_API_MOCK=false and NEXT_PUBLIC_API_BASE=https://... at build time.
//
// Every request sends an X-Player-Id header: a random UUID kept in localStorage. It is not an
// account and not a login; it only lets the server group one browser's watches together.
//
// The data types (Sphere, StarTarget, Forecast, Discovery) come from the shared contract. The wire
// shapes for traps and jobs below (Trap, CreateTrapRequest, HuntResponse, Job) are NOT defined in
// the contract; they are this client's working assumption until the api/ session publishes its own.

import type { Discovery, Forecast, Sphere, StarTarget } from "@/lib/contract";
import { MOCK_DISCOVERIES } from "@/lib/mock/discoveries";
import { mockForecast, type ForecastWindow } from "@/lib/mock/forecast";
import { radecToVec, separationDeg } from "@/lib/sky";

// ---------- config ----------

export const API_MOCK = process.env.NEXT_PUBLIC_API_MOCK !== "false";
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

// ---------- wire types (assumed, see header) ----------

/** A watch is created on a sky patch or on a star. */
export type CreateTrapRequest = { sphere: Sphere } | { star: StarTarget; sphere?: Sphere };

export type Trap = {
  id: string;
  created_at: string;
  mode: "explore";
} & CreateTrapRequest;

export type HuntRequest = { trap_id: string };
export type HuntResponse = { job_id: string };

export type JobStatus = "queued" | "running" | "done" | "failed";
export type Job = {
  id: string;
  trap_id: string;
  status: JobStatus;
  /** 0 to 1 while running. */
  progress: number;
  discovery_ids: string[];
  created_at: string;
  error?: string;
};

export type ForecastQuery = { sphere: Sphere; window?: ForecastWindow | { start: string; end: string } };

export type DiscoveryQuery = {
  trap_id?: string;
  type?: Discovery["type"];
  source?: Discovery["source"];
  limit?: number;
};

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ---------- player id ----------

const PLAYER_KEY = "planet-hunter:player-id";
let memoryPlayerId: string | null = null;

/** Stable per-browser UUID. Falls back to an in-memory id when storage is blocked. */
export function getPlayerId(): string {
  if (typeof window === "undefined") return "server";
  try {
    const existing = localStorage.getItem(PLAYER_KEY);
    if (existing) return existing;
    const id = crypto.randomUUID();
    localStorage.setItem(PLAYER_KEY, id);
    return id;
  } catch {
    return (memoryPlayerId ??= crypto.randomUUID());
  }
}

// ---------- real transport ----------

async function request<T>(method: string, path: string, body?: unknown, query?: Record<string, string | number | undefined>): Promise<T> {
  const url = new URL(`${API_BASE}${path}`, typeof window === "undefined" ? "http://localhost" : window.location.origin);
  for (const [k, v] of Object.entries(query ?? {})) if (v !== undefined) url.searchParams.set(k, String(v));
  const res = await fetch(url, {
    method,
    headers: {
      "X-Player-Id": getPlayerId(),
      ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const j = await res.json();
      msg = j.detail ?? j.error ?? msg;
    } catch {}
    throw new ApiError(res.status, typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

function windowRange(w: ForecastQuery["window"]): { start: string; end: string } {
  if (w && typeof w === "object") return w;
  const start = new Date();
  const days = w === "week" ? 7 : 1;
  return { start: start.toISOString(), end: new Date(start.getTime() + days * 86400000).toISOString() };
}

// ---------- mock transport ----------

const MOCK_TRAPS_KEY = "planet-hunter:mock-traps:v1";
const mockJobs = new Map<string, { job: Job; startedAt: number }>();

/**
 * Screens that know the Rubin footprint (the sky map) register a lookup so mock forecasts give
 * zero visit chance outside it. Without one, the mock guesses from declination alone.
 */
let footprintLabelOf: (ra: number, dec: number) => string = (_ra, dec) => (dec > 30 ? "outside" : "lowdust");
export function setMockFootprintResolver(fn: (ra: number, dec: number) => string) {
  footprintLabelOf = fn;
}

const delay = (ms = 120 + Math.random() * 180) => new Promise((r) => setTimeout(r, ms));

function readMockTraps(): Trap[] {
  try {
    return JSON.parse(localStorage.getItem(MOCK_TRAPS_KEY) ?? "[]");
  } catch {
    return [];
  }
}
function writeMockTraps(traps: Trap[]) {
  try {
    localStorage.setItem(MOCK_TRAPS_KEY, JSON.stringify(traps));
  } catch {}
}

function trapCenter(t: Trap): Sphere | null {
  return "sphere" in t && t.sphere ? t.sphere : null;
}

/** Mock jobs advance with wall-clock time: queued, then running for ~4 s, then done. */
function advance(entry: { job: Job; startedAt: number }): Job {
  const age = Date.now() - entry.startedAt;
  const j = entry.job;
  if (age < 800) return { ...j, status: "queued", progress: 0 };
  if (age < 4800) return { ...j, status: "running", progress: Math.min(0.99, (age - 800) / 4000) };
  return { ...j, status: "done", progress: 1 };
}

const mock = {
  async createTrap(req: CreateTrapRequest): Promise<Trap> {
    await delay();
    const trap = { ...req, id: crypto.randomUUID(), created_at: new Date().toISOString(), mode: "explore" } as Trap;
    writeMockTraps([...readMockTraps(), trap]);
    return trap;
  },
  async listTraps(): Promise<Trap[]> {
    await delay();
    return readMockTraps();
  },
  async deleteTrap(id: string): Promise<void> {
    await delay();
    const traps = readMockTraps();
    if (!traps.some((t) => t.id === id)) throw new ApiError(404, "No watch with that id");
    writeMockTraps(traps.filter((t) => t.id !== id));
  },
  async getForecast(q: ForecastQuery): Promise<Forecast> {
    await delay(60);
    const w = typeof q.window === "string" || q.window === undefined ? (q.window ?? "tonight") : "week";
    return mockForecast(q.sphere, w, footprintLabelOf(q.sphere.ra_deg, q.sphere.dec_deg));
  },
  async hunt(req: HuntRequest): Promise<HuntResponse> {
    await delay();
    const trap = readMockTraps().find((t) => t.id === req.trap_id);
    if (!trap) throw new ApiError(404, "No watch with that id");
    // Detections inside the watched patch, if any; otherwise one or two demo records.
    const c = trapCenter(trap);
    let ids = c
      ? MOCK_DISCOVERIES.filter((d) => separationDeg(radecToVec(c.ra_deg, c.dec_deg), radecToVec(d.ra_deg, d.dec_deg)) <= c.radius_deg).map((d) => d.id)
      : [];
    if (!ids.length) ids = MOCK_DISCOVERIES.slice(0, 1 + (trap.id.charCodeAt(0) % 2)).map((d) => d.id);
    const job: Job = { id: crypto.randomUUID(), trap_id: trap.id, status: "queued", progress: 0, discovery_ids: ids, created_at: new Date().toISOString() };
    mockJobs.set(job.id, { job, startedAt: Date.now() });
    return { job_id: job.id };
  },
  async getJob(id: string): Promise<Job> {
    await delay(80);
    const entry = mockJobs.get(id);
    if (!entry) throw new ApiError(404, "No job with that id");
    const j = advance(entry);
    return j.status === "done" ? j : { ...j, discovery_ids: [] };
  },
  async listDiscoveries(q: DiscoveryQuery = {}): Promise<Discovery[]> {
    await delay();
    let list = MOCK_DISCOVERIES;
    if (q.trap_id) {
      const done = [...mockJobs.values()].map(advance).filter((j) => j.trap_id === q.trap_id && j.status === "done");
      const ids = new Set(done.flatMap((j) => j.discovery_ids));
      list = list.filter((d) => ids.has(d.id));
    }
    if (q.type) list = list.filter((d) => d.type === q.type);
    if (q.source) list = list.filter((d) => d.source === q.source);
    return list.slice(0, q.limit ?? list.length);
  },
  async getDiscovery(id: string): Promise<Discovery> {
    await delay();
    const d = MOCK_DISCOVERIES.find((x) => x.id === id);
    if (!d) throw new ApiError(404, "No detection with that id");
    return d;
  },
};

// ---------- public client ----------

export const api = {
  /** POST /traps */
  createTrap: (req: CreateTrapRequest): Promise<Trap> => (API_MOCK ? mock.createTrap(req) : request("POST", "/traps", req)),
  /** GET /traps */
  listTraps: (): Promise<Trap[]> => (API_MOCK ? mock.listTraps() : request("GET", "/traps")),
  /** DELETE /traps/{id} */
  deleteTrap: (id: string): Promise<void> => (API_MOCK ? mock.deleteTrap(id) : request("DELETE", `/traps/${encodeURIComponent(id)}`)),
  /** GET /forecast?ra_deg&dec_deg&radius_deg&start&end */
  getForecast: (q: ForecastQuery): Promise<Forecast> => {
    if (API_MOCK) return mock.getForecast(q);
    const { start, end } = windowRange(q.window);
    return request("GET", "/forecast", undefined, { ...q.sphere, start, end });
  },
  /** POST /hunt: start analyzing a watch. The UI calls this "Analyze". */
  hunt: (req: HuntRequest): Promise<HuntResponse> => (API_MOCK ? mock.hunt(req) : request("POST", "/hunt", req)),
  /** GET /jobs/{id} */
  getJob: (id: string): Promise<Job> => (API_MOCK ? mock.getJob(id) : request("GET", `/jobs/${encodeURIComponent(id)}`)),
  /** GET /discoveries */
  listDiscoveries: (q: DiscoveryQuery = {}): Promise<Discovery[]> =>
    API_MOCK ? mock.listDiscoveries(q) : request("GET", "/discoveries", undefined, q),
  /** GET /discoveries/{id} */
  getDiscovery: (id: string): Promise<Discovery> =>
    API_MOCK ? mock.getDiscovery(id) : request("GET", `/discoveries/${encodeURIComponent(id)}`),
};

/** Poll a job until it finishes. Resolves with the final job; rejects on failure or abort. */
export async function waitForJob(id: string, opts: { intervalMs?: number; signal?: AbortSignal; onProgress?: (j: Job) => void } = {}): Promise<Job> {
  const interval = opts.intervalMs ?? 1000;
  for (;;) {
    if (opts.signal?.aborted) throw new DOMException("Aborted", "AbortError");
    const job = await api.getJob(id);
    opts.onProgress?.(job);
    if (job.status === "done") return job;
    if (job.status === "failed") throw new ApiError(500, job.error ?? "Analysis failed");
    await new Promise((r) => setTimeout(r, interval));
  }
}

// Typed client for the planet finder API (api/README.md). The site is the planet finder only (v2).
//
// MOCK mode is ON by default: it serves web/public/data/finder/* (see below). For a real server, set
// NEXT_PUBLIC_API_MOCK=false and NEXT_PUBLIC_API_BASE. In live mode each call maps the API's JSON onto
// the shapes below, which the finder's components are written against.

import type { SkyEvent } from "@/lib/contract";

export const API_MOCK = process.env.NEXT_PUBLIC_API_MOCK !== "false";
export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function getJson<T>(url: string, signal?: AbortSignal, headers?: HeadersInit): Promise<T> {
  const res = await fetch(url, { signal, headers });
  if (!res.ok) throw new ApiError(res.status, `${url}: ${res.status}`);
  return res.json() as Promise<T>;
}

// ---------- Sky events: removed in v2 ----------
//
// The events API and its mock are gone (docs/REMOVED.md). These two stay only because the current home page
// still imports them (components/home/ThisWeek.tsx); MONITOR-UI's new home page drops them. No events, ever.

/** @deprecated Sky events were removed; always empty. */
export async function getAllEvents(): Promise<SkyEvent[]> {
  return [];
}

/** @deprecated The events mock's pinned clock is gone: the real clock. */
export async function clockNow(): Promise<number> {
  return Date.now();
}

/** A response plus what in it is a stand-in. `standIn` names what the data was borrowed from. */
export type Served<T> = { data: T; demo: boolean; standIn: string | null };

// ---------- Finder: planet candidates from the nightly search ----------
//
// Candidate comes from HUNT, PixelVet from PIXELS, `vetting` from VET; the API (api/README.md, Planet Finder)
// stores them with the votes. MOCK mode serves public/data/finder/* (built by
// components/finder/data/build-finder-mock.mjs): made-up candidates with simulated light curves, and pixel
// images borrowed from two real PIXELS runs. Live mode maps the API's JSON onto the same shapes.

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
  /** "periodic" (default), "single" or "duo": a single dip has no period yet (period_d null in the API). */
  kind?: string;
  /** VET's vetting block, as stored; null until VET has vetted it. */
  vetting?: Record<string, unknown> | null;
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
  if (!API_MOCK) return liveCandidates(signal);
  const ix = await finderMockIndex();
  return { run_at: ix.meta.run_at, funnel: ix.meta.funnel, candidates: ix.candidates.map((c) => ({ ...c, votes: withMyVote(c.id, c.votes) })), demo: true };
}

export async function getCandidate(id: string, signal?: AbortSignal): Promise<CandidateReport> {
  if (!API_MOCK) {
    const r = await getJson<ApiReport>(`${API_BASE}/finder/candidates/${encodeURIComponent(id)}`, signal, { "X-Voter-Key": voterKey() });
    return { candidate: { ...r.candidate, radius_rjup: radiusOf(r.candidate) }, pixels: r.pixel_vet, votes: toVotes(r.votes, r.my_vote), demo: false };
  }
  if (!/^[a-z0-9_-]+$/i.test(id)) throw new ApiError(404, `No candidate ${id}`);
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
      headers: { "content-type": "application/json", "X-Voter-Key": voterKey() },
      body: JSON.stringify({ vote, reason_chips: reasons }),
    });
    if (!res.ok) throw new ApiError(res.status, `vote: ${res.status}`);
    const body = (await res.json()) as { vote: VoteChoice | null; reason_chips: string[]; votes: ApiVotes };
    myVotes.write(id, body.vote ? { vote: body.vote, reasons: body.reason_chips } : null);
    return toVotes(body.votes, body.vote ? { vote: body.vote, reason_chips: body.reason_chips } : null);
  }
  const base = (await finderMockIndex()).candidates.find((c) => c.id === id)?.votes;
  if (!base) throw new ApiError(404, `No candidate ${id}`);
  await new Promise((ok) => setTimeout(ok, 250));
  myVotes.write(id, vote ? { vote, reasons } : null);
  return withMyVote(id, base);
}

export async function getSensitivity(signal?: AbortSignal): Promise<Served<Sensitivity>> {
  if (!API_MOCK) return { data: (await getJson<{ sensitivity: Sensitivity }>(`${API_BASE}/finder/sensitivity`, signal)).sensitivity, demo: false, standIn: null };
  return { data: await getJson<Sensitivity>("/data/finder/sensitivity.mock.json", signal), demo: true, standIn: null };
}

// ---------- Live-mode mapping ----------

/** This browser's random voter id (the API stores only its SHA-256). Made once, kept in localStorage. */
let memoryKey: string | null = null;
export function voterKey(): string {
  const make = () => Array.from(crypto.getRandomValues(new Uint8Array(24)), (b) => b.toString(16).padStart(2, "0")).join("");
  try {
    let key = localStorage.getItem("ph-voter-key");
    if (!key || !/^[A-Za-z0-9_-]{16,128}$/.test(key)) {
      key = make();
      localStorage.setItem("ph-voter-key", key);
    }
    return key;
  } catch {
    return (memoryKey ??= make()); // private mode: one id until reload
  }
}

type ApiVotes = { planet: number; fake: number; unsure: number; total: number };
type ApiRadius = { radius_rjup?: number | (number | null)[] | null; radius_rjup_best?: number | null; radius_low?: number | null; radius_high?: number | null };
type ApiRow = Omit<CandidateRow, "votes" | "radius_rjup"> & ApiRadius & { votes: ApiVotes };
type ApiReport = {
  candidate: Omit<Candidate, "radius_rjup"> & ApiRadius;
  pixel_vet: PixelVet | null;
  votes: ApiVotes;
  my_vote: { vote: VoteChoice; reason_chips: string[] } | null;
};
type ApiFunnel = { sweep_at: string | null; stages: { stage: string; count: number; source: string }[] };

/** One radius for the UI: hunt's best estimate, else the middle of its [low, high] range. */
function radiusOf(c: ApiRadius): number {
  if (typeof c.radius_rjup_best === "number") return c.radius_rjup_best;
  if (typeof c.radius_rjup === "number") return c.radius_rjup;
  const [lo, hi] = [c.radius_low, c.radius_high];
  return lo != null && hi != null ? (lo + hi) / 2 : (lo ?? hi ?? Number.NaN);
}

function toVotes(v: ApiVotes, mine: { vote: VoteChoice; reason_chips: string[] } | null): Votes {
  return { planet: v.planet, fake: v.fake, unsure: v.unsure, my_vote: mine?.vote ?? null, my_reasons: mine?.reason_chips ?? [] };
}

async function liveCandidates(signal?: AbortSignal): Promise<CandidateList> {
  const rows: ApiRow[] = [];
  let cursor: string | null = null;
  do {
    const q: string = `limit=200${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`;
    const page: { items: ApiRow[]; next_cursor: string | null } = await getJson(`${API_BASE}/finder/candidates?${q}`, signal);
    rows.push(...page.items);
    cursor = page.next_cursor;
  } while (cursor && rows.length < 2000);
  const funnel = await getJson<ApiFunnel>(`${API_BASE}/finder/funnel`, signal);
  const mine = myVotes.read();
  return {
    run_at: funnel.sweep_at ?? new Date().toISOString(),
    funnel: funnel.stages.map((st) => ({ key: st.stage.toLowerCase().replace(/[^a-z0-9]+/g, "_"), label: st.stage, count: st.count })),
    candidates: rows.map((r) => ({
      ...r,
      radius_rjup: radiusOf(r),
      votes: toVotes(r.votes, mine[r.id] ? { vote: mine[r.id].vote, reason_chips: mine[r.id].reasons } : null),
    })),
    demo: false,
  };
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

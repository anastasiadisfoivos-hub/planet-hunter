// Typed client for the planet finder API (api/README.md). The site is the planet finder only (v2).
//
// With NEXT_PUBLIC_API_BASE set, the site talks to that API and shows only what it answers, an empty
// candidate list included. Without it, MOCK mode serves web/public/data/monitor/* (see below), where the
// candidates are stand-ins and say so. In live mode each call maps the API's JSON onto the shapes below,
// which the components are written against.

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");
export const API_MOCK = API_BASE === "";

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

/** A response plus what in it is a stand-in. `standIn` names what the data was borrowed from. */
export type Served<T> = { data: T; demo: boolean; standIn: string | null };

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
  /** Null when the API has no searched star yet. */
  star: MonitorStar | null;
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
  /** What the search kept at each step, over the same stars: the one source for every count on the site. */
  funnel?: FunnelStep[];
};

// The API's monitor answers (api/README.md, Monitor), mapped onto the shapes above.
type ApiNow = { mode: MonitorMode; run_started_at: string | null; star: MonitorStar | null; next_tic?: number | null };
type ApiLogItem = { tic: number; outcome: string | null; detections_count: number; searched_at: string; record?: LogStar | null };
type ApiStats = { stars_searched: number; signals: number; candidates: number; rejected_by_reason?: Record<string, number>; rejected?: number; known?: number; last_run_at: string | null; funnel?: FunnelStep[] };
const MAX_LOG = 200;

const OUTCOMES: StarOutcome[] = ["candidate", "known", "rejected", "none"];

/** A log row from the API: its stored record when still kept, else the bare row. */
function logStar(i: ApiLogItem): LogStar {
  const outcome = OUTCOMES.includes(i.outcome as StarOutcome) ? (i.outcome as StarOutcome) : "none";
  if (i.record) return { ...i.record, outcome, searched_at: i.searched_at };
  return {
    tic: i.tic, tmag: null, teff: null, radius_rsun: null, ra: 0, dec: 0, sectors: [],
    observed_from: null, observed_to: null, detections: [], outcome, searched_at: i.searched_at,
  }; // prettier-ignore
}

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
    const r = await getJson<ApiNow>(`${API_BASE}/monitor/now${q}`, opts.signal);
    return { mode: r.mode, star: r.star, replay_of: r.mode === "replay" ? r.run_started_at : null, next_tic: r.next_tic ?? null };
  }
  const { order } = await replay();
  const i = opts.after == null ? 0 : (order.indexOf(opts.after) + 1) % order.length;
  const star = await getJson<MonitorStar>(`${MON}/stars/${order[i]}.json`, opts.signal);
  return { mode: "replay", star, replay_of: MOCK_REPLAY_OF, next_tic: order[(i + 1) % order.length] };
}

export async function getMonitorLog(signal?: AbortSignal): Promise<MonitorLog> {
  if (API_MOCK) return getJson<MonitorLog>(`${MON}/log.json`, signal);
  const r = await getJson<{ items: ApiLogItem[] }>(`${API_BASE}/monitor/log?limit=${MAX_LOG}&detail=true`, signal);
  return { stars: r.items.map(logStar) };
}

export async function getMonitorCoverage(signal?: AbortSignal): Promise<MonitorCoverage> {
  if (API_MOCK) return getJson<MonitorCoverage>(`${MON}/coverage.json`, signal);
  const r = await getJson<{ stars?: (Omit<CoverageStar, "ra" | "dec"> & { ra: number | null; dec: number | null })[] }>(`${API_BASE}/monitor/coverage`, signal);
  // a star stored without a position can't go on the sky
  return { stars: (r.stars ?? []).filter((x): x is CoverageStar => x.ra != null && x.dec != null) };
}

export async function getMonitorStats(signal?: AbortSignal): Promise<MonitorStats> {
  if (API_MOCK) return getJson<MonitorStats>(`${MON}/stats.json`, signal);
  const r = await getJson<ApiStats>(`${API_BASE}/monitor/stats`, signal);
  const at = r.last_run_at ?? new Date().toISOString();
  const rejected = r.rejected ?? Object.values(r.rejected_by_reason ?? {}).reduce((a, b) => a + b, 0);
  return { since: at, updated_at: at, stars_searched: r.stars_searched, signals: r.signals, candidates: r.candidates, rejected, known: r.known ?? 0, funnel: r.funnel };
}

export type Sparks = { unit: "ppm"; bins: number; stars: Record<string, number[]> };
let sparksFile: Promise<Sparks | null> | null = null;

/**
 * Row-sized traces for the log: every searched star's whole curve in about 180 points (each keeps its lowest
 * value, so dips survive). The mock has one for every star it downloaded; a live API without the route gives none,
 * and the log says "no curve stored".
 */
export function getSparks(): Promise<Sparks | null> {
  sparksFile ??= API_MOCK
    ? getJson<Sparks>(`${MON}/sparks.json`).catch(() => null)
    : getJson<Sparks>(`${API_BASE}/monitor/sparks`).catch(() => null);
  return sparksFile;
}

/** A searched star's light curve: the mock's file, or the API's latest stored record of it. */
export async function getStarCurve(tic: number, signal?: AbortSignal): Promise<MonitorStar | null> {
  if (!API_MOCK) return getJson<MonitorStar>(`${API_BASE}/monitor/stars/${tic}`, signal).catch(() => null);
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
  /** "periodic" (default), "single" or "duo": a single dip has no period yet (period_d null in the API). */
  kind?: string;
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

/**
 * VET's block (vet/README.md). The mock writes an older shape (gaia_id, can_mimic, needed_depth, a yes/no
 * gaia_variable, no `ran` on gaia and variability); skyvet writes source_id, could_mimic, required_depth, an object
 * for gaia_variable, and `ran` everywhere. Both are accepted; components/finder/vetting.ts reads them.
 */
export type Vetting = {
  leo: { ran: boolean; passed: boolean | null; flags: string[]; reason?: string };
  triceratops: { ran: boolean; fpp: number | null; nfpp: number | null; reason?: string };
  gaia: {
    ran?: boolean;
    reason?: string;
    ruwe: number | null;
    neighbours: {
      gaia_id?: string;
      source_id?: string;
      sep_arcsec: number;
      gmag: number;
      can_mimic?: boolean | null;
      could_mimic?: boolean | null;
      needed_depth?: number | null;
      required_depth?: number | null;
    }[];
    binary_hint: boolean | null;
    gaia_id?: string | null;
    source_id?: string | null;
    radius_arcsec?: number;
    n_could_mimic?: number;
  };
  variability: {
    ran?: boolean;
    reason?: string;
    vsx_match: { name: string; type: string; sep_arcsec: number; period_d: number | null } | null;
    gaia_variable: boolean | { phot_variable_flag?: string | null; class?: string | null } | null;
  };
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

/** The search's funnel, from /monitor/stats: the same counts the monitor's tally shows. */
async function statsFunnel(signal?: AbortSignal): Promise<FunnelStep[] | null> {
  const st = await getMonitorStats(signal).catch(() => null);
  return st?.funnel ?? null;
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
  if (!API_MOCK) {
    const [list, funnel] = await Promise.all([liveCandidates(signal), statsFunnel(signal)]);
    return { ...list, funnel: funnel ?? list.funnel };
  }
  const [ix, funnel] = await Promise.all([candMockIndex(), statsFunnel(signal)]);
  return { run_at: ix.run_at, funnel: funnel ?? [], candidates: ix.candidates.map((c) => ({ ...c, votes: withMyVote(c.id, c.votes) })), demo: true };
}

export async function getCandidate(id: string, signal?: AbortSignal): Promise<CandidateReport> {
  if (!API_MOCK) {
    const r = await getJson<ApiReport>(`${API_BASE}/finder/candidates/${encodeURIComponent(id)}`, signal, { "X-Voter-Key": voterKey() });
    return { candidate: { ...r.candidate, radius_rjup: radiusOf(r.candidate), stand_in: null }, pixels: r.pixel_vet, votes: toVotes(r.votes, r.my_vote), demo: false };
  }
  if (!/^[a-z0-9_-]+$/i.test(id)) throw new ApiError(404, `No candidate ${id}`);
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
      headers: { "content-type": "application/json", "X-Voter-Key": voterKey() },
      body: JSON.stringify({ vote, reason_chips: reasons }),
    });
    if (!res.ok) throw new ApiError(res.status, `vote: ${res.status}`);
    const body = (await res.json()) as { vote: VoteChoice | null; reason_chips: string[]; votes: ApiVotes };
    myVotes.write(id, body.vote ? { vote: body.vote, reasons: body.reason_chips } : null);
    return toVotes(body.votes, body.vote ? { vote: body.vote, reason_chips: body.reason_chips } : null);
  }
  const base = (await candMockIndex()).candidates.find((c) => c.id === id)?.votes;
  if (!base) throw new ApiError(404, `No candidate ${id}`);
  await new Promise((ok) => setTimeout(ok, 250));
  myVotes.write(id, vote ? { vote, reasons } : null);
  return withMyVote(id, base);
}

export async function getSensitivity(signal?: AbortSignal): Promise<Served<Sensitivity>> {
  if (!API_MOCK) return { data: (await getJson<{ sensitivity: Sensitivity }>(`${API_BASE}/finder/sensitivity`, signal)).sensitivity, demo: false, standIn: null };
  return { data: await getJson<Sensitivity>(`${MON}/sensitivity.json`, signal), demo: true, standIn: null };
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
      stand_in: null, // stand-ins are the mock's alone: the live list is only what the search kept
      votes: toVotes(r.votes, mine[r.id] ? { vote: mine[r.id].vote, reason_chips: mine[r.id].reasons } : null),
    })),
    demo: false,
  };
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

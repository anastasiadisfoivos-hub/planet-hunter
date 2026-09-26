// The Finder's pure logic: words and units, the list's filters and sort, the vote box's state, the CTOI file.
// No React and no "@/" value imports, so node --test can load it directly.

import type { Candidate, CandidateRow, KnownListResult, PixelVerdict, VoteChoice, Votes } from "@/lib/api";

export const REARTH_PER_RJUP = 11.209;
export const BTJD_TO_BJD = 2457000;

// ---------- words and units ----------

/** A period people can read: hours under a day, days otherwise. Never scientific notation. */
export function fmtPeriod(d: number): string {
  if (d < 1) return `${(d * 24).toFixed(1)} h`;
  if (d < 100) return `${d.toFixed(2)} d`;
  return `${Math.round(d)} d`;
}

export const rEarth = (rjup: number) => rjup * REARTH_PER_RJUP;

/** "1.8 × Earth" for small planets, "0.72 × Jupiter" for big ones. */
export function fmtSize(rjup: number): string {
  const re = rEarth(rjup);
  return re < 6 ? `${re.toFixed(1)} × Earth` : `${rjup.toFixed(2)} × Jupiter`;
}

export function sizeClass(rjup: number): string {
  const re = rEarth(rjup);
  if (re < 1.25) return "Earth-sized";
  if (re < 2) return "super-Earth";
  if (re < 3.5) return "sub-Neptune";
  if (re < 6) return "Neptune-sized";
  if (re < 10) return "Saturn-sized";
  if (re < 16) return "Jupiter-sized";
  return "bigger than Jupiter";
}

export function fmtDepth(ppm: number): string {
  return ppm >= 1000 ? `${(ppm / 1e4).toFixed(2)}%` : `${Math.round(ppm)} ppm`;
}

export const CHECK_LABELS: Record<string, { label: string; unit?: string }> = {
  snr: { label: "Signal strength", unit: "× noise" },
  odd_even: { label: "Odd and even dips match", unit: "σ apart" },
  secondary_eclipse: { label: "No second dip halfway round", unit: "σ" },
  size: { label: "Planet-sized", unit: "R♃" },
  transit_count: { label: "Enough dips", unit: "dips" },
  depth_consistency: { label: "Same depth every sector", unit: "σ change" },
};

export function checkLabel(name: string): string {
  return CHECK_LABELS[name]?.label ?? name.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

export function fmtCheckValue(name: string, v: number | string | null): string {
  if (v == null) return "not measured";
  if (typeof v === "string") return v;
  const unit = CHECK_LABELS[name]?.unit;
  const n = Number.isInteger(v) ? v.toString() : Math.abs(v) >= 100 ? Math.round(v).toString() : Math.abs(v) >= 10 ? v.toFixed(1) : v.toFixed(2).replace(/\.?0+$/, "");
  return unit ? `${n} ${unit}` : n;
}

export const SCORE_PARTS: Record<string, { label: string; text: string }> = {
  signal: { label: "Signal", text: "How far the dip stands above the noise (SNR and SDE)." },
  shape: { label: "Shape", text: "Flat-bottomed and U-shaped like a planet, rather than V-shaped like a grazing star." },
  checks: { label: "Checks", text: "Share of the checks passed; each failed check lowers it." },
  pixels: { label: "Pixels", text: "How likely the dip is on the target star, from the pixel check." },
};

export const partLabel = (k: string) => SCORE_PARTS[k]?.label ?? k.replace(/_/g, " ");

export const KNOWN_LISTS: { key: "confirmed" | "toi" | "ctoi" | "eb"; label: string; source: string; url: string }[] = [
  { key: "confirmed", label: "Confirmed planets", source: "NASA Exoplanet Archive", url: "https://exoplanetarchive.ipac.caltech.edu/" },
  { key: "toi", label: "TESS Objects of Interest", source: "TOI catalogue, ExoFOP", url: "https://exofop.ipac.caltech.edu/tess/view_toi.php" },
  { key: "ctoi", label: "Community TOIs", source: "CTOI catalogue, ExoFOP", url: "https://exofop.ipac.caltech.edu/tess/view_ctoi.php" },
  { key: "eb", label: "Eclipsing binaries", source: "TESS EB catalogue", url: "https://archive.stsci.edu/hlsp/tess-ebs" },
];

export function listMatch(v: KnownListResult): { matched: boolean; id: string | null } {
  if (typeof v === "boolean") return { matched: v, id: null };
  return { matched: !!v?.matched, id: v?.id ?? null };
}

export const VERDICTS: { value: PixelVerdict; label: string }[] = [
  { value: "on target", label: "On target" },
  { value: "possible neighbour", label: "Possible neighbour" },
  { value: "off target", label: "Off target" },
  { value: "inconclusive", label: "Inconclusive" },
];

export const verdictLabel = (v: PixelVerdict | null) => VERDICTS.find((x) => x.value === v)?.label ?? "Not checked yet";

// ---------- light-curve helpers ----------

/** Mid-transit times that fall inside [t0, t1]. */
export function transitTimes(epoch: number, period: number, t0: number, t1: number): number[] {
  const out: number[] = [];
  for (let n = Math.ceil((t0 - epoch) / period); epoch + n * period <= t1; n++) out.push(epoch + n * period);
  return out;
}

/** Median-bin a folded curve (x in hours from mid-transit) into `n` bins over [-half, half]. */
export function binFolded(hours: number[], flux: number[], half: number, n: number): { x: number; y: number }[] {
  const bins: number[][] = Array.from({ length: n }, () => []);
  hours.forEach((h, k) => {
    if (h < -half || h >= half) return;
    bins[Math.floor(((h + half) / (2 * half)) * n)].push(flux[k]);
  });
  return bins.flatMap((b, i) => {
    if (b.length < 3) return [];
    const s = [...b].sort((p, q) => p - q);
    return [{ x: -half + ((i + 0.5) * 2 * half) / n, y: s[s.length >> 1] }];
  });
}

// ---------- the candidate list: filters and sort ----------

export type Range = { id: string; label: string; min: number; max: number };

/** Sizes in Earth radii. */
export const SIZE_RANGES: Range[] = [
  { id: "any", label: "Any size", min: 0, max: Infinity },
  { id: "small", label: "Under 2 × Earth", min: 0, max: 2 },
  { id: "subnep", label: "2 to 4 × Earth", min: 2, max: 4 },
  { id: "nep", label: "4 to 8 × Earth", min: 4, max: 8 },
  { id: "giant", label: "Over 8 × Earth", min: 8, max: Infinity },
];

/** Periods in days. */
export const PERIOD_RANGES: Range[] = [
  { id: "any", label: "Any period", min: 0, max: Infinity },
  { id: "ultrashort", label: "Under 1 day", min: 0, max: 1 },
  { id: "short", label: "1 to 5 days", min: 1, max: 5 },
  { id: "mid", label: "5 to 10 days", min: 5, max: 10 },
  { id: "long", label: "Over 10 days", min: 10, max: Infinity },
];

/** Candidates with fewer votes than this show up under "Needs votes". */
export const NEEDS_VOTES_BELOW = 10;

export type Filters = { size: string; period: string; verdicts: PixelVerdict[]; needsVotes: boolean };
export const NO_FILTERS: Filters = { size: "any", period: "any", verdicts: [], needsVotes: false };

export const totalVotes = (v: Votes) => v.planet + v.fake + v.unsure;

const inRange = (ranges: Range[], id: string, v: number) => {
  const r = ranges.find((x) => x.id === id) ?? ranges[0];
  return v >= r.min && v < r.max;
};

export function filterCandidates(rows: CandidateRow[], f: Filters): CandidateRow[] {
  return rows.filter(
    (c) =>
      inRange(SIZE_RANGES, f.size, rEarth(c.radius_rjup)) &&
      inRange(PERIOD_RANGES, f.period, c.period_d) &&
      (f.verdicts.length === 0 || (c.pixel_verdict != null && f.verdicts.includes(c.pixel_verdict))) &&
      (!f.needsVotes || totalVotes(c.votes) < NEEDS_VOTES_BELOW),
  );
}

export const activeFilterCount = (f: Filters) => (f.size !== "any" ? 1 : 0) + (f.period !== "any" ? 1 : 0) + (f.verdicts.length ? 1 : 0) + (f.needsVotes ? 1 : 0);

export type SortKey = "score" | "period" | "size" | "votes" | "created";
export type Sort = { key: SortKey; dir: "asc" | "desc" };
export const DEFAULT_SORT: Sort = { key: "score", dir: "desc" };

export const SORTS: { key: SortKey; label: string; firstDir: "asc" | "desc" }[] = [
  { key: "score", label: "Priority", firstDir: "desc" },
  { key: "period", label: "Period", firstDir: "asc" },
  { key: "size", label: "Size", firstDir: "asc" },
  { key: "votes", label: "Votes", firstDir: "asc" },
  { key: "created", label: "Newest", firstDir: "desc" },
];

const sortValue = (c: CandidateRow, k: SortKey): number =>
  k === "score" ? c.score : k === "period" ? c.period_d : k === "size" ? c.radius_rjup : k === "votes" ? totalVotes(c.votes) : Date.parse(c.created_at);

/** Stable: ties keep priority order (highest first), then id. */
export function sortCandidates(rows: CandidateRow[], s: Sort): CandidateRow[] {
  const sign = s.dir === "asc" ? 1 : -1;
  return [...rows].sort((a, b) => sign * (sortValue(a, s.key) - sortValue(b, s.key)) || b.score - a.score || a.id.localeCompare(b.id));
}

/** Clicking a column: the same column flips direction, a new one starts at its natural direction. */
export function nextSort(cur: Sort, key: SortKey): Sort {
  if (cur.key === key) return { key, dir: cur.dir === "asc" ? "desc" : "asc" };
  return { key, dir: SORTS.find((x) => x.key === key)?.firstDir ?? "desc" };
}

// ---------- the vote box ----------

export const REASONS: { id: string; label: string }[] = [
  { id: "v_shaped", label: "V-shaped" },
  { id: "depth_changes", label: "Depth changes" },
  { id: "off_target", label: "Off-target" },
  { id: "too_few_dips", label: "Too few dips" },
];

export type VoteState = {
  counts: { planet: number; fake: number; unsure: number };
  mine: VoteChoice | null;
  reasons: string[];
  status: "idle" | "saving" | "saved" | "error";
  error: string | null;
  /** The last state the server confirmed, restored when a save fails. */
  confirmed: { counts: VoteState["counts"]; mine: VoteChoice | null; reasons: string[] };
};

export type VoteAction =
  | { type: "choose"; choice: VoteChoice }
  | { type: "toggleReason"; id: string }
  | { type: "saved"; votes: Votes }
  | { type: "failed"; message: string };

/**
 * The tally is shown only after you have voted, so the crowd cannot anchor your judgement (DESIGN.md, Words).
 * Before that, only the number of people who voted is known.
 */
export function visibleCounts(s: Pick<VoteState, "counts" | "mine">): { counts: VoteState["counts"] | null; total: number } {
  const total = s.counts.planet + s.counts.fake + s.counts.unsure;
  return { counts: s.mine ? s.counts : null, total };
}

export function initVotes(v: Votes): VoteState {
  const counts = { planet: v.planet, fake: v.fake, unsure: v.unsure };
  const reasons = v.my_reasons ?? [];
  return { counts, mine: v.my_vote, reasons, status: "idle", error: null, confirmed: { counts, mine: v.my_vote, reasons } };
}

/**
 * Votes show at once and save in the background. Choosing your current vote again takes it back
 * (and drops its reasons). Reasons can only be added once you have voted. A failed save puts back
 * what the server last confirmed.
 */
export function voteReducer(s: VoteState, a: VoteAction): VoteState {
  switch (a.type) {
    case "choose": {
      const counts = { ...s.counts };
      if (s.mine) counts[s.mine] = Math.max(0, counts[s.mine] - 1);
      const mine = s.mine === a.choice ? null : a.choice;
      if (mine) counts[mine] += 1;
      return { ...s, counts, mine, reasons: mine ? s.reasons : [], status: "saving", error: null };
    }
    case "toggleReason": {
      if (!s.mine) return s;
      const reasons = s.reasons.includes(a.id) ? s.reasons.filter((r) => r !== a.id) : [...s.reasons, a.id];
      return { ...s, reasons, status: "saving", error: null };
    }
    case "saved": {
      const counts = { planet: a.votes.planet, fake: a.votes.fake, unsure: a.votes.unsure };
      const reasons = a.votes.my_reasons ?? s.reasons;
      return { counts, mine: a.votes.my_vote, reasons, status: "saved", error: null, confirmed: { counts, mine: a.votes.my_vote, reasons } };
    }
    case "failed":
      return { ...s, ...s.confirmed, status: "error", error: a.message };
  }
}

// ---------- ExoFOP CTOI file ----------

export const CTOI_COLUMNS = [
  "TIC ID",
  "Previous CTOI",
  "Hosted By",
  "Epoch (BJD)",
  "Epoch Err",
  "Period (days)",
  "Period Err",
  "Depth (ppm)",
  "Depth Err",
  "Duration (hrs)",
  "Duration Err",
  "Radius (R_Earth)",
  "Radius Err",
  "Comments",
];

const csvCell = (v: string | number) => {
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
};

/** One row per candidate. Uncertainties the search doesn't give are left empty for the API to fill. */
export function ctoiCsv(cands: Candidate[]): string {
  const rows = cands.map((c) => [
    c.tic,
    "",
    "planet-hunter",
    (c.t0_btjd + BTJD_TO_BJD).toFixed(5),
    "",
    c.period_d.toFixed(6),
    "",
    Math.round(c.depth_ppm),
    "",
    c.duration_h.toFixed(2),
    "",
    rEarth(c.radius_rjup).toFixed(2),
    ((rEarth(c.radius_high) - rEarth(c.radius_low)) / 2).toFixed(2),
    `Candidate from TESS sectors ${c.sectors.join(" ")}; SNR ${c.snr.toFixed(1)}; ${c.n_transits} transits; score ${c.score.toFixed(2)}`,
  ]);
  return [CTOI_COLUMNS, ...rows].map((r) => r.map(csvCell).join(",")).join("\n") + "\n";
}

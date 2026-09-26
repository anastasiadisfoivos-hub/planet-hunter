import { test } from "node:test";
import assert from "node:assert/strict";
import type { CandidateRow, Votes } from "../../lib/api.ts";
import {
  activeFilterCount,
  ctoiCsv,
  DEFAULT_SORT,
  filterCandidates,
  fmtPeriod,
  initVotes,
  nextSort,
  NO_FILTERS,
  sortCandidates,
  voteReducer,
  type VoteState,
} from "../../components/finder/finder.ts";

// ---------- fixtures ----------

const votes = (planet: number, fake: number, unsure: number): Votes => ({ planet, fake, unsure, my_vote: null });

function row(id: string, o: Partial<CandidateRow>): CandidateRow {
  return {
    id,
    tic: 1,
    name: null,
    period_d: 3,
    t0_btjd: 3000,
    duration_h: 2,
    depth_ppm: 1000,
    snr: 12,
    sde: 9,
    n_transits: 6,
    sectors: [90],
    radius_rjup: 0.3,
    radius_low: 0.26,
    radius_high: 0.34,
    score: 0.5,
    score_parts: {},
    known_lists: { confirmed: false, toi: false, ctoi: false, eb: false },
    created_at: "2026-09-20T00:00:00Z",
    checks_passed: 6,
    checks_total: 6,
    pixel_verdict: "on target",
    votes: votes(0, 0, 0),
    ...o,
  };
}

// radius_rjup × 11.209 = Earth radii: 0.1 → 1.1, 0.25 → 2.8, 0.5 → 5.6, 1.0 → 11.2
const ROWS = [
  row("a", { score: 0.9, period_d: 0.7, radius_rjup: 0.1, votes: votes(20, 3, 1), created_at: "2026-09-18T00:00:00Z" }),
  row("b", { score: 0.8, period_d: 3.2, radius_rjup: 0.25, pixel_verdict: "possible neighbour", votes: votes(1, 2, 0), created_at: "2026-09-22T00:00:00Z" }),
  row("c", { score: 0.7, period_d: 12.4, radius_rjup: 1.0, pixel_verdict: "off target", votes: votes(4, 9, 3) }),
  row("d", { score: 0.6, period_d: 6.1, radius_rjup: 0.5, pixel_verdict: "inconclusive", votes: votes(0, 0, 0) }),
  row("e", { score: 0.8, period_d: 4.9, radius_rjup: 0.25, votes: votes(5, 5, 5) }),
];
const ids = (rs: CandidateRow[]) => rs.map((r) => r.id).join("");

// ---------- filters ----------

test("no filters keeps every candidate", () => {
  assert.equal(ids(filterCandidates(ROWS, NO_FILTERS)), "abcde");
  assert.equal(activeFilterCount(NO_FILTERS), 0);
});

test("size filter works in Earth radii from the Jupiter-radius field", () => {
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, size: "small" })), "a");
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, size: "subnep" })), "be");
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, size: "giant" })), "c");
});

test("period filter: ranges include their lower edge", () => {
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, period: "ultrashort" })), "a");
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, period: "short" })), "be");
  assert.equal(ids(filterCandidates([row("x", { period_d: 5 })], { ...NO_FILTERS, period: "mid" })), "x");
});

test("pixel verdict filter: several verdicts are OR'ed; a candidate not checked yet never matches", () => {
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, verdicts: ["off target", "inconclusive"] })), "cd");
  assert.equal(ids(filterCandidates([row("x", { pixel_verdict: null })], { ...NO_FILTERS, verdicts: ["on target"] })), "");
});

test("needs votes: fewer than 10 votes in total", () => {
  assert.equal(ids(filterCandidates(ROWS, { ...NO_FILTERS, needsVotes: true })), "bd");
});

test("filters combine with AND and are counted", () => {
  const f = { size: "subnep", period: "short", verdicts: ["on target" as const], needsVotes: false };
  assert.equal(ids(filterCandidates(ROWS, f)), "e");
  assert.equal(activeFilterCount(f), 3);
});

// ---------- sort ----------

test("default sort is score, highest first; ties fall back to id", () => {
  assert.equal(ids(sortCandidates(ROWS, DEFAULT_SORT)), "abecd");
});

test("sort by period, size, votes and newest", () => {
  assert.equal(ids(sortCandidates(ROWS, { key: "period", dir: "asc" })), "abedc");
  assert.equal(ids(sortCandidates(ROWS, { key: "period", dir: "desc" })), "cdeba");
  // b and e share a size: the tie keeps score order, then id.
  assert.equal(ids(sortCandidates(ROWS, { key: "size", dir: "asc" })), "abedc");
  // totals: a 24, b 3, c 16, d 0, e 15
  assert.equal(ids(sortCandidates(ROWS, { key: "votes", dir: "asc" })), "dbeca");
  // c, d and e share a date: score order breaks the tie.
  assert.equal(ids(sortCandidates(ROWS, { key: "created", dir: "desc" })), "becda");
});

test("sorting does not mutate the input", () => {
  const copy = [...ROWS];
  sortCandidates(ROWS, { key: "period", dir: "asc" });
  assert.deepEqual(ROWS, copy);
});

test("clicking a column: same column flips, a new column starts at its natural direction", () => {
  assert.deepEqual(nextSort(DEFAULT_SORT, "score"), { key: "score", dir: "asc" });
  assert.deepEqual(nextSort(DEFAULT_SORT, "period"), { key: "period", dir: "asc" });
  assert.deepEqual(nextSort({ key: "period", dir: "asc" }, "period"), { key: "period", dir: "desc" });
  assert.deepEqual(nextSort({ key: "period", dir: "asc" }, "created"), { key: "created", dir: "desc" });
});

// ---------- vote box ----------

const start = () => initVotes({ planet: 5, fake: 2, unsure: 1, my_vote: null, my_reasons: [] });

test("a vote shows at once and is marked saving", () => {
  const s = voteReducer(start(), { type: "choose", choice: "planet" });
  assert.deepEqual(s.counts, { planet: 6, fake: 2, unsure: 1 });
  assert.equal(s.mine, "planet");
  assert.equal(s.status, "saving");
});

test("changing a vote moves it, it is never counted twice", () => {
  let s = voteReducer(start(), { type: "choose", choice: "planet" });
  s = voteReducer(s, { type: "choose", choice: "fake" });
  assert.deepEqual(s.counts, { planet: 5, fake: 3, unsure: 1 });
  assert.equal(s.mine, "fake");
});

test("choosing your vote again takes it back and drops its reasons", () => {
  let s = voteReducer(start(), { type: "choose", choice: "fake" });
  s = voteReducer(s, { type: "toggleReason", id: "v_shaped" });
  assert.deepEqual(s.reasons, ["v_shaped"]);
  s = voteReducer(s, { type: "choose", choice: "fake" });
  assert.equal(s.mine, null);
  assert.deepEqual(s.counts, { planet: 5, fake: 2, unsure: 1 });
  assert.deepEqual(s.reasons, []);
});

test("reasons need a vote first, and toggle on and off", () => {
  const s0 = voteReducer(start(), { type: "toggleReason", id: "v_shaped" });
  assert.deepEqual(s0.reasons, []);
  assert.equal(s0.status, "idle");
  let s = voteReducer(start(), { type: "choose", choice: "unsure" });
  s = voteReducer(s, { type: "toggleReason", id: "too_few_dips" });
  s = voteReducer(s, { type: "toggleReason", id: "depth_changes" });
  s = voteReducer(s, { type: "toggleReason", id: "too_few_dips" });
  assert.deepEqual(s.reasons, ["depth_changes"]);
});

test("the server's totals win when a save lands", () => {
  let s = voteReducer(start(), { type: "choose", choice: "planet" });
  s = voteReducer(s, { type: "saved", votes: { planet: 9, fake: 2, unsure: 1, my_vote: "planet", my_reasons: [] } });
  assert.deepEqual(s.counts, { planet: 9, fake: 2, unsure: 1 });
  assert.equal(s.status, "saved");
  assert.deepEqual(s.confirmed.counts, s.counts);
});

test("a failed save restores the last confirmed state and says why", () => {
  let s: VoteState = voteReducer(start(), { type: "choose", choice: "planet" });
  s = voteReducer(s, { type: "saved", votes: { planet: 6, fake: 2, unsure: 1, my_vote: "planet", my_reasons: [] } });
  s = voteReducer(s, { type: "choose", choice: "fake" });
  s = voteReducer(s, { type: "failed", message: "offline" });
  assert.equal(s.mine, "planet");
  assert.deepEqual(s.counts, { planet: 6, fake: 2, unsure: 1 });
  assert.equal(s.status, "error");
  assert.equal(s.error, "offline");
});

test("an earlier vote from this viewer is restored on load", () => {
  const s = initVotes({ planet: 3, fake: 1, unsure: 0, my_vote: "fake", my_reasons: ["off_target"] });
  assert.equal(s.mine, "fake");
  assert.deepEqual(s.reasons, ["off_target"]);
});

// ---------- units and export ----------

test("periods read in hours or days, never scientific notation", () => {
  assert.equal(fmtPeriod(0.7784), "18.7 h");
  assert.equal(fmtPeriod(3.8127), "3.81 d");
  assert.equal(fmtPeriod(412.3), "412 d");
});

test("CTOI file: header plus one row per candidate, BJD epoch, readable comment", () => {
  const csv = ctoiCsv([
    { ...row("a", {}), t0_btjd: 3000.12345, period_d: 3.8127, sectors: [81, 82], checks: [], folded: { phase: [], flux: [] }, unfolded: { time_btjd: [], flux: [] } },
  ]);
  const lines = csv.trim().split("\n");
  assert.equal(lines.length, 2);
  assert.ok(lines[0].startsWith("TIC ID,Previous CTOI,"));
  assert.ok(lines[1].includes(",2460000.12345,"));
  assert.ok(lines[1].includes(",3.812700,"));
  assert.ok(lines[1].endsWith(",Candidate from TESS sectors 81 82; SNR 12.0; 6 transits; score 0.50"));
});

test("vote counts stay hidden until you vote, then show; taking the vote back hides them again", async () => {
  const { visibleCounts } = await import("../../components/finder/finder.ts");
  const v: Votes = { planet: 41, fake: 6, unsure: 9, my_vote: null };
  let st = initVotes(v);
  assert.deepEqual(visibleCounts(st), { counts: null, total: 56 });
  st = voteReducer(st, { type: "choose", choice: "planet" });
  assert.deepEqual(visibleCounts(st), { counts: { planet: 42, fake: 6, unsure: 9 }, total: 57 });
  st = voteReducer(st, { type: "choose", choice: "planet" });
  assert.equal(visibleCounts(st).counts, null);
  assert.equal(visibleCounts(initVotes({ ...v, my_vote: "unsure" })).counts?.unsure, 9, "a returning voter sees the tally");
});

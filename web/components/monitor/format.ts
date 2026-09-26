// Words and numbers for the monitor, the log and the dossier (DESIGN.md: Numbers and units, Words).
// No React and no "@/" value imports, so node --test can load it directly.

import type { Detection, DetectionOutcome, MonitorMode, StarOutcome } from "@/lib/api";

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const THIN = " ";

export const BTJD_EPOCH_JD = 2457000;

/** BTJD (BJD - 2457000) to a JS time in ms. Close enough for dates (BJD vs UTC differs by minutes). */
export function btjdToMs(t: number): number {
  return (t + BTJD_EPOCH_JD - 2440587.5) * 86400000;
}

function parts(iso: string | number) {
  const d = new Date(iso);
  return { d: d.getUTCDate(), m: d.getUTCMonth(), y: d.getUTCFullYear(), hh: d.getUTCHours(), mm: d.getUTCMinutes() };
}

/** "19 Sep 2026" */
export function fmtDate(iso: string | number): string {
  const p = parts(iso);
  return `${p.d} ${MONTHS[p.m]} ${p.y}`;
}

/** "19 Sep" */
export function fmtDay(iso: string | number): string {
  const p = parts(iso);
  return `${p.d} ${MONTHS[p.m]}`;
}

/** "19 Sep 2026, 07:57 UTC" */
export function fmtDateTime(iso: string | number): string {
  const p = parts(iso);
  return `${fmtDate(iso)}, ${String(p.hh).padStart(2, "0")}:${String(p.mm).padStart(2, "0")} UTC`;
}

/**
 * The data dates, said plainly: "2 to 28 Aug 2026", "18 Jul to 12 Aug 2026", "30 Dec 2025 to 24 Jan 2026".
 * Spans over a year apart become "Jul 2023 to Jun 2026".
 */
export function fmtSpan(from: string, to: string): string {
  const a = parts(from);
  const b = parts(to);
  if (b.y - a.y > 1 || (b.y !== a.y && b.m >= a.m)) return `${MONTHS[a.m]} ${a.y} to ${MONTHS[b.m]} ${b.y}`;
  if (a.y !== b.y) return `${a.d} ${MONTHS[a.m]} ${a.y} to ${b.d} ${MONTHS[b.m]} ${b.y}`;
  if (a.m !== b.m) return `${a.d} ${MONTHS[a.m]} to ${b.d} ${MONTHS[b.m]} ${b.y}`;
  if (a.d !== b.d) return `${a.d} to ${b.d} ${MONTHS[b.m]} ${b.y}`;
  return `${a.d} ${MONTHS[a.m]} ${a.y}`;
}

/** "observed 2 to 28 Aug 2026 by TESS", with the sector count when there are several. */
export function observedLine(from: string | null, to: string | null, sectors: number[]): string {
  if (!from || !to) return sectors.length ? `TESS ${sectorWord(sectors)}` : "no TESS data";
  const n = sectors.length > 1 ? `, ${sectors.length} sectors` : "";
  return `observed ${fmtSpan(from, to)} by TESS${n}`;
}

export function sectorWord(sectors: number[]): string {
  if (!sectors.length) return "";
  return sectors.length === 1 ? `sector ${sectors[0]}` : `sectors ${sectors.join(", ")}`;
}

/** Thousands with a thin space: 48 721. */
export function thousands(n: number): string {
  return Math.round(n)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, THIN);
}

/** ppm under 1000, % above: "840 ppm", "0.79%". */
export function fmtDepth(ppm: number | null): string {
  if (ppm == null) return "depth not measured";
  return ppm >= 1000 ? `${(ppm / 1e4).toFixed(2)}%` : `${thousands(ppm)} ppm`;
}

/** Hours under a day, days otherwise. Never scientific notation. */
export function fmtPeriod(d: number | null): string {
  if (d == null) return "one dip";
  if (d < 1) return `${(d * 24).toFixed(1)} h`;
  if (d < 100) return `${d.toFixed(2)} d`;
  return `${Math.round(d)} d`;
}

export function fmtTemp(k: number | null): string {
  return k == null ? "temperature unknown" : `${thousands(k)} K`;
}

export function fmtRadius(r: number | null): string {
  return r == null ? "size unknown" : `${r.toFixed(2)} R☉`;
}

export function fmtTmag(t: number | null): string {
  return t == null ? "" : `T ${t.toFixed(1)}`;
}

/** A plain-language kind of star from its temperature and radius (TIC values). */
export function starKind(teff: number | null, radius: number | null): string {
  if (teff == null) return "a star";
  const giant = radius != null && radius > 3;
  const sub = radius != null && radius > 1.6 && !giant;
  let type: string;
  if (teff < 3900) type = "M";
  else if (teff < 5300) type = "K";
  else if (teff < 6000) type = "G";
  else if (teff < 7500) type = "F";
  else if (teff < 10000) type = "A";
  else type = "B";
  if (giant) return `${type === "M" || type === "K" ? "a red" : "an evolved"} giant`;
  const an = (w: string) => `${"AFM".includes(w[0]) ? "an" : "a"} ${w}`; // "an F", "an M", "a K"
  if (sub) return an(`${type} subgiant`);
  return an(type === "A" || type === "B" ? `${type} star` : `${type} dwarf`);
}

export const OUTCOME_WORD: Record<StarOutcome, string> = {
  candidate: "candidate",
  known: "known",
  rejected: "rejected",
  none: "nothing found",
};

const KIND_WORD: Record<Detection["kind"], string> = { periodic: "repeating", duo: "two dips", single: "one dip" };

/** The short tick label: "repeating, every 2.34 d · 5 090 ppm". */
export function detectionLabel(d: Detection): string {
  const every = d.kind === "periodic" && d.period_d != null ? `every ${fmtPeriod(d.period_d)}` : KIND_WORD[d.kind];
  return `${every} · ${fmtDepth(d.depth_ppm)}`;
}

/** What the live text twin says when a dip is marked. */
export function detectionSentence(d: Detection, whenMs: number): string {
  const verdict: Record<DetectionOutcome, string> = { candidate: "kept as a candidate", known: "already known", rejected: "rejected" };
  return `Dip at ${fmtDay(whenMs)}, ${fmtDepth(d.depth_ppm)}, ${verdict[d.outcome]}. ${d.reason}`;
}

/** The mode, said plainly: "Live", or "Replay of the 26 Sep 2026 search". */
export function modeLabel(mode: MonitorMode, replayOf: string | null): string {
  if (mode === "live") return "Live";
  return replayOf ? `Replay of the ${fmtDate(replayOf)} search` : "Replay";
}

/** The short form for the top bar. */
export function modeShort(mode: MonitorMode): string {
  return mode === "live" ? "LIVE" : "REPLAY";
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${thousands(n)} ${n === 1 ? one : many}`;
}

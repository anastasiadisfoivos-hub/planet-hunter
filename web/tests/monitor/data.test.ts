// The mock data keeps the promises the pages make: one source for every count, and a curve for every star it stored.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (f: string) => JSON.parse(readFileSync(new URL(`../../public/data/monitor/${f}`, import.meta.url), "utf8"));
const stats = read("stats.json");
const log = read("log.json").stars as { tic: number; detections: { stage?: string }[] }[];
const sparks = read("sparks.json").stars as Record<string, number[]>;

test("one source for counts: the tally and the funnel agree with the log", () => {
  const funnel = Object.fromEntries((stats.funnel as { key: string; count: number }[]).map((f) => [f.key, f.count]));
  assert.equal(stats.stars_searched, log.length);
  assert.equal(funnel.stars, stats.stars_searched, "funnel and tally count the same stars");
  const found = log.flatMap((s) => s.detections).filter((d) => d.stage !== "masked").length;
  assert.equal(stats.signals, found);
  assert.equal(funnel.signals, stats.signals, "funnel and tally count the same signals");
  assert.equal(funnel.candidates, stats.candidates);
});

test("every star in the log has its light curve for the row trace", () => {
  const missing = log.filter((s) => !sparks[String(s.tic)]?.length).map((s) => s.tic);
  assert.deepEqual(missing, []);
  assert.ok(Object.values(sparks).every((v) => v.length >= 100 && v.every(Number.isFinite)));
});

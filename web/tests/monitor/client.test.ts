import { test } from "node:test";
import assert from "node:assert/strict";
import { LIVE_POLL_MS, MonitorClient, RETRY_MS, type FetchNow } from "../../components/monitor/client.ts";
import type { MonitorNow, MonitorStar } from "../../lib/api.ts";

const star = (tic: number): MonitorStar => ({
  tic,
  tmag: 10,
  teff: 5000,
  radius_rsun: 1,
  ra: 0,
  dec: 0,
  sectors: [82],
  observed_from: "2024-08-10T21:36:31Z",
  observed_to: "2024-09-05T18:00:18Z",
  lightcurve: { t: [0, 1], f: [1, 1] },
  detections: [],
  outcome: "none",
  searched_at: "2026-09-26T07:22:52Z",
});

/** A replay server over `order`, recording each `after` it was asked for. */
function replayServer(order: number[]) {
  const calls: (number | null)[] = [];
  const fetchNow: FetchNow = async ({ after }) => {
    calls.push(after ?? null);
    const i = after == null ? 0 : (order.indexOf(after) + 1) % order.length;
    return { mode: "replay", star: star(order[i]), replay_of: "2026-09-26T07:57:39Z", next_tic: order[(i + 1) % order.length] };
  };
  return { fetchNow, calls };
}

const noSleep = async () => {};

test("replay: starts at the first star and walks the order, wrapping round", async () => {
  const { fetchNow } = replayServer([11, 22, 33]);
  const c = new MonitorClient(fetchNow, noSleep);
  const seen = [(await c.start()).star.tic];
  for (let k = 0; k < 4; k++) seen.push((await c.advance()).star.tic);
  assert.deepEqual(seen, [11, 22, 33, 11, 22]);
});

test("replay: the next star is fetched while the current one draws, once", async () => {
  const { fetchNow, calls } = replayServer([11, 22, 33]);
  const c = new MonitorClient(fetchNow, noSleep);
  await c.start();
  await new Promise((ok) => setImmediate(ok));
  assert.deepEqual(calls, [null, 11], "prefetched the star after 11 straight after starting");
  await c.advance();
  assert.deepEqual(calls, [null, 11, 22], "advancing used the prefetch and prefetched the next one");
});

test("replay: the mode stays replay and says what it replays", async () => {
  const { fetchNow } = replayServer([11, 22]);
  const c = new MonitorClient(fetchNow, noSleep);
  const now = await c.start();
  assert.equal(now.mode, "replay");
  assert.equal(now.replay_of, "2026-09-26T07:57:39Z");
});

test("live: waits while the server is still on the same star, then moves on", async () => {
  const answers = [101, 101, 101, 202];
  const waits: number[] = [];
  const fetchNow: FetchNow = async () => ({ mode: "live", star: star(answers.shift() ?? 202), replay_of: null, next_tic: null });
  const c = new MonitorClient(fetchNow, async (ms) => {
    waits.push(ms);
  });
  assert.equal((await c.start()).star.tic, 101);
  const next = await c.advance();
  assert.equal(next.star.tic, 202);
  assert.equal(next.mode, "live");
  assert.deepEqual(waits, [LIVE_POLL_MS, LIVE_POLL_MS]);
});

test("failures retry with a growing wait and report each retry", async () => {
  let fails = 3;
  const waits: number[] = [];
  const retries: number[] = [];
  const fetchNow: FetchNow = async () => {
    if (fails-- > 0) throw new Error("503");
    return { mode: "replay", star: star(7), replay_of: null, next_tic: null } satisfies MonitorNow;
  };
  const c = new MonitorClient(fetchNow, async (ms) => {
    waits.push(ms);
  });
  c.onRetry = (n) => retries.push(n);
  assert.equal((await c.start()).star.tic, 7);
  assert.deepEqual(waits.slice(0, 3), RETRY_MS.slice(0, 3));
  assert.deepEqual(retries.slice(0, 3), [1, 2, 3]);
});

test("an abort stops the retries", async () => {
  const ac = new AbortController();
  const fetchNow: FetchNow = async () => {
    throw new Error("down");
  };
  const c = new MonitorClient(fetchNow, async () => {
    ac.abort();
  });
  await assert.rejects(c.start(ac.signal));
});

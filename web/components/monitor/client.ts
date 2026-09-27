// The monitor's data client: which star to draw now and which comes next (DESIGN.md: The monitor).
// Replay: asks for the star after the one just drawn, and fetches it while the current one draws.
// Live: asks the server what it is searching now; if that is still the star just drawn, waits and asks again.
// Failures retry with a growing wait. No React and no "@/" value imports, so node --test can load it.

import type { MonitorNow } from "@/lib/api";

export type FetchNow = (opts: { after?: number | null; signal?: AbortSignal }) => Promise<MonitorNow>;
export type Sleep = (ms: number, signal?: AbortSignal) => Promise<void>;

export const RETRY_MS = [1000, 3000, 10000, 30000];
export const LIVE_POLL_MS = 20000;

export const sleep: Sleep = (ms, signal) =>
  new Promise((ok, fail) => {
    if (signal?.aborted) return fail(signal.reason);
    const id = setTimeout(ok, ms);
    signal?.addEventListener(
      "abort",
      () => {
        clearTimeout(id);
        fail(signal.reason);
      },
      { once: true },
    );
  });

export class MonitorClient {
  readonly #fetch: FetchNow;
  readonly #sleep: Sleep;
  #current: MonitorNow | null = null;
  #next: Promise<MonitorNow> | null = null;
  #nextAfter: number | null = null;
  /** Called when a fetch fails and the client is about to retry (for a quiet status line). */
  onRetry: ((attempt: number, error: unknown) => void) | null = null;

  constructor(fetchNow: FetchNow, wait: Sleep = sleep) {
    this.#fetch = fetchNow;
    this.#sleep = wait;
  }

  get current(): MonitorNow | null {
    return this.#current;
  }

  /** Fetch, retrying failures with a growing wait until it works or `signal` aborts. */
  async #get(after: number | null, signal?: AbortSignal): Promise<MonitorNow> {
    for (let attempt = 0; ; attempt++) {
      try {
        return await this.#fetch({ after, signal });
      } catch (e) {
        if (signal?.aborted) throw e;
        this.onRetry?.(attempt + 1, e);
        await this.#sleep(RETRY_MS[Math.min(attempt, RETRY_MS.length - 1)], signal);
      }
    }
  }

  #prefetch(signal?: AbortSignal) {
    const cur = this.#current;
    if (!cur || cur.mode !== "replay") return;
    this.#nextAfter = cur.star.tic;
    this.#next = this.#get(cur.star.tic, signal);
    this.#next.catch(() => {}); // an abort here is handled by whoever awaits it
  }

  /** The first star. */
  async start(signal?: AbortSignal): Promise<MonitorNow> {
    this.#current = await this.#get(null, signal);
    this.#prefetch(signal);
    return this.#current;
  }

  /** The star after the current one: prefetched in a replay, polled for when live. */
  async advance(signal?: AbortSignal): Promise<MonitorNow> {
    const cur = this.#current;
    if (!cur) return this.start(signal);
    let next: MonitorNow;
    if (cur.mode === "replay") {
      next = this.#next && this.#nextAfter === cur.star.tic ? await this.#next : await this.#get(cur.star.tic, signal);
    } else {
      next = await this.#get(null, signal);
      while (next.mode === "live" && next.star.tic === cur.star.tic) {
        await this.#sleep(LIVE_POLL_MS, signal);
        next = await this.#get(null, signal);
      }
    }
    this.#current = next;
    this.#next = null;
    this.#prefetch(signal);
    return next;
  }
}

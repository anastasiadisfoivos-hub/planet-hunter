"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

/**
 * Width of an element in CSS pixels, tracked with a ResizeObserver. Charts draw in real pixels.
 * A callback ref, so it also works for elements that mount after data loads.
 */
export function useWidth<T extends HTMLElement>(fallback = 640) {
  const [width, setWidth] = useState(fallback);
  const ro = useRef<ResizeObserver | null>(null);
  const ref = useCallback((el: T | null) => {
    ro.current?.disconnect();
    ro.current = null;
    if (!el) return;
    const obs = new ResizeObserver(([e]) => setWidth(Math.max(240, Math.floor(e.contentRect.width))));
    obs.observe(el);
    ro.current = obs;
  }, []);
  return [ref, width] as const;
}

const RM = "(prefers-reduced-motion: reduce)";

/** True when the viewer asked for reduced motion. */
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(RM);
      m.addEventListener("change", cb);
      return () => m.removeEventListener("change", cb);
    },
    () => window.matchMedia(RM).matches,
    () => false,
  );
}

/** Fetch JSON once. */
export function useJson<T>(url: string | null) {
  const [state, setState] = useState<{ url: string | null; data: T | null; error: string | null }>({ url: null, data: null, error: null });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!url) return;
    const ctl = new AbortController();
    fetch(url, { signal: ctl.signal })
      .then((r) => {
        if (!r.ok) throw new Error(`${url}: ${r.status}`);
        return r.json() as Promise<T>;
      })
      .then((data) => setState({ url, data, error: null }))
      .catch((e: unknown) => !ctl.signal.aborted && setState({ url, data: null, error: e instanceof Error ? e.message : String(e) }));
    return () => ctl.abort();
  }, [url, attempt]);
  const fresh = state.url === url;
  return {
    data: fresh ? state.data : null,
    error: fresh ? state.error : null,
    retry: () => {
      setState({ url: null, data: null, error: null });
      setAttempt((n) => n + 1);
    },
  };
}

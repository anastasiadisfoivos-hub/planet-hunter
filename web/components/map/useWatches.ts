"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, setMockFootprintResolver, type Trap } from "@/lib/api";
import type { Forecast, Sphere } from "@/lib/contract";
import { footprintLabel, type MapData } from "@/lib/data";
import type { ForecastWindow } from "@/lib/mock/forecast";
import { useStore, type Draft, type Watch } from "@/state/store";

/** Api Trap -> map Watch. Star watches get their host's name from the local host list. */
export function toWatch(t: Trap, nameByTic: Map<string, string>): Watch | null {
  if ("star" in t) {
    const sphere = t.sphere;
    if (!sphere) return null;
    return { id: t.id, sphere, createdAt: t.created_at, kind: "star", target: t.star, name: nameByTic.get(String(t.star.tic_id)) ?? `TIC ${t.star.tic_id}` };
  }
  return { id: t.id, sphere: t.sphere, createdAt: t.created_at, kind: "sky" };
}

/** Loads watches from the api and exposes create/remove. */
export function useWatchesApi(data: MapData) {
  const { dispatch } = useStore();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const nameByTic = useRef(new Map(data.hosts.tic.map((tic, i) => [String(tic), data.hosts.name[i]])));

  useEffect(() => {
    // Mock forecasts should know where Rubin actually looks.
    setMockFootprintResolver((ra, dec) => footprintLabel(data.footprint, ra, dec));
    let live = true;
    api
      .listTraps()
      .then((traps) => {
        if (!live) return;
        dispatch({ type: "watches", watches: traps.map((t) => toWatch(t, nameByTic.current)).filter((w): w is Watch => !!w) });
      })
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [data.footprint, dispatch]);

  const create = useCallback(
    async (draft: Draft) => {
      if (draft.result.kind === "blocked") return;
      setBusy(true);
      setError(null);
      try {
        const req = draft.result.kind === "star" ? { star: draft.result.target, sphere: draft.sphere } : { sphere: draft.sphere };
        const trap = await api.createTrap(req);
        const watch = toWatch(trap, nameByTic.current);
        if (watch) dispatch({ type: "watchAdded", watch });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [dispatch],
  );

  const remove = useCallback(
    async (id: string) => {
      setError(null);
      try {
        await api.deleteTrap(id);
        dispatch({ type: "watchRemoved", id });
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    },
    [dispatch],
  );

  return { create, remove, busy, error };
}

/** Latest-wins forecast for the sphere being drawn. Keeps the previous result while the next loads. */
export function useForecast(sphere: Sphere | null, win: ForecastWindow) {
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [error, setError] = useState<string | null>(null);
  const seq = useRef(0);
  const key = sphere ? `${sphere.ra_deg},${sphere.dec_deg},${sphere.radius_deg},${win}` : "";

  useEffect(() => {
    if (!sphere) return;
    const n = ++seq.current;
    api
      .getForecast({ sphere, window: win })
      .then((f) => {
        if (n === seq.current) {
          setForecast(f);
          setError(null);
        }
      })
      .catch((e: unknown) => n === seq.current && setError(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { forecast: sphere ? forecast : null, error };
}

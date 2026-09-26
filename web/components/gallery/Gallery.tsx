"use client";

// /events: every event's own picture, newest first, grouped by UTC day. The filter bar and its URL params are the
// sky's (components/map/FilterBar.tsx, urlFilters.ts), so a filtered link works on /events and /sky alike.

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { FilterBar } from "@/components/map/FilterBar";
import { filtersFromParams, paramsWithFilters } from "@/components/map/urlFilters";
import { Button, DemoTag } from "@/components/ui";
import { API_MOCK, clockNow, getAllEvents } from "@/lib/api";
import type { SkyEvent } from "@/lib/contract";
import { applyFilters } from "@/lib/events";
import { StoreProvider, useStore } from "@/state/store";
import { EventTile } from "./EventTile";
import { dayGroup } from "./text";
import s from "./gallery.module.css";

const SIZES = "(max-width: 639px) 50vw, (max-width: 1023px) 33vw, (max-width: 1279px) 25vw, 262px";

export function Gallery() {
  return (
    <StoreProvider>
      <GalleryView />
    </StoreProvider>
  );
}

function GalleryView() {
  const { state, dispatch } = useStore();
  const [data, setData] = useState<{ events: SkyEvent[]; now: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Filters from a shared link, applied before the first render of the grid.
  useEffect(() => {
    dispatch({ type: "filters", patch: filtersFromParams(new URLSearchParams(window.location.search)) });
  }, [dispatch]);

  useEffect(() => {
    let live = true;
    Promise.all([getAllEvents(), clockNow()])
      .then(([events, now]) => live && setData({ events, now }))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [attempt]);

  // Keep the address bar in step with the filters (replaceState: a filter change is not a page).
  useEffect(() => {
    const cur = new URLSearchParams(window.location.search);
    const next = paramsWithFilters(state.filters, cur);
    if (next.toString() === cur.toString()) return;
    const q = next.toString().replace(/%2C/g, ",");
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${q ? `?${q}` : ""}`);
  }, [state.filters]);

  // The same filters as a query, for the Pictures | Sky switch.
  const query = useMemo(() => paramsWithFilters(state.filters, new URLSearchParams()).toString().replace(/%2C/g, ","), [state.filters]);
  const shown = useMemo(() => (data ? applyFilters(data.events, state.filters, data.now) : []), [data, state.filters]);
  const groups = useMemo(() => {
    const out: { label: string; events: SkyEvent[] }[] = [];
    if (!data) return out;
    for (const e of shown) {
      const label = dayGroup(e.observed_at, data.now);
      const last = out.at(-1);
      if (last?.label === label) last.events.push(e);
      else out.push({ label, events: [e] });
    }
    return out;
  }, [shown, data]);

  return (
    <main className={`wrap ${s.page}`}>
      <div className={s.head}>
        <div>
          <h1 className={s.h1}>Events</h1>
          <p className={s.count} aria-live="polite">
            {data ? (
              <>
                <span className="mono">{shown.length}</span> {shown.length === 1 ? "event" : "events"}, newest first.
              </>
            ) : (
              " "
            )}
          </p>
        </div>
        <div className={s.headEnd}>
          {API_MOCK && <DemoTag />}
          <nav className={s.view} aria-label="View">
            <Link href={`/events${query ? `?${query}` : ""}`} aria-current="page">
              Pictures
            </Link>
            <Link href={`/sky${query ? `?${query}` : ""}`}>Sky</Link>
          </nav>
        </div>
      </div>

      {error ? (
        <div className={s.note} role="alert">
          <p>The events didn&apos;t load. {error}</p>
          <Button
            variant="ghost"
            onClick={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </Button>
        </div>
      ) : !data ? (
        <div className={s.grid} aria-busy="true" aria-label="Loading events">
          {Array.from({ length: 10 }, (_, i) => (
            <div key={i} className={s.skeleton} />
          ))}
        </div>
      ) : (
        <>
          <div className={s.bar}>
            <FilterBar events={data.events} now={data.now} inflow />
          </div>
          {groups.length === 0 ? (
            <div className={s.note}>
              <p>No events match these filters.</p>
              <Button variant="ghost" onClick={() => dispatch({ type: "resetFilters" })}>
                Reset filters
              </Button>
            </div>
          ) : (
            groups.map((g) => (
              <section key={g.label} className={s.day} aria-label={g.label}>
                <div className={s.dayHead}>
                  <h2 className="label">{g.label}</h2>
                  <span className="label">{g.events.length}</span>
                </div>
                <div className={s.grid}>
                  {g.events.map((e) => (
                    <EventTile key={e.id} event={e} sizes={SIZES} />
                  ))}
                </div>
              </section>
            ))
          )}
        </>
      )}
    </main>
  );
}

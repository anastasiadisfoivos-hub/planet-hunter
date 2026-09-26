"use client";

import { useEffect, useState } from "react";
import { Button, DemoTag, EmptyState } from "@/components/ui";
import { getEvents, API_MOCK, type EventsPage } from "@/lib/api";
import { CATEGORY_OF, type SkyEvent } from "@/lib/contract";
import { SOURCE_LABEL, TYPE_LABEL } from "@/lib/events";
import { formatAgo } from "@/lib/format";
import { useStore } from "@/state/store";
import { CategoryGlyph } from "./CategoryGlyph";
import { CLEAR_LABEL, EMPTY_TITLE } from "./filterModel";
import s from "./map.module.css";

const PAGE = 30;

/** Thumbnail for a feed row: the event's first picture (thumb_url), or its category glyph. */
function Thumb({ e }: { e: SkyEvent }) {
  const img = e.images[0];
  if (!img) {
    return (
      <span className={s.thumbEmpty} aria-hidden>
        <CategoryGlyph category={CATEGORY_OF[e.type]} size={14} />
      </span>
    );
  }
  const cutout = img.kind.startsWith("cutout_");
  return (
    // eslint-disable-next-line @next/next/no-img-element -- remote survey thumbnails, pre-checked by PICTURES
    <img className={s.thumb} src={img.thumb_url ?? img.url} alt="" loading="lazy" decoding="async" data-pixelated={cutout || undefined} />
  );
}

function pictureNote(e: SkyEvent): string | null {
  const k = e.images[0]?.kind;
  if (k === "sky_context") return "archive photo";
  if (k === "forecast_map") return "forecast map";
  return null;
}

export function Feed({ now, onOpen }: { now: number; onOpen: (id: string) => void }) {
  const { state, dispatch } = useStore();
  const [pages, setPages] = useState<{ key: string; data: EventsPage } | null>(null);
  const [more, setMore] = useState<{ key: string; events: SkyEvent[]; next: string | null } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  const key = JSON.stringify(state.filters) + attempt;

  useEffect(() => {
    const ctl = new AbortController();
    getEvents(state.filters, { limit: PAGE, signal: ctl.signal })
      .then((data) => {
        setPages({ key, data });
        setError(null);
      })
      .catch((e: unknown) => !ctl.signal.aborted && setError(e instanceof Error ? e.message : String(e)));
    return () => ctl.abort();
  }, [state.filters, key]);

  const loading = !pages || pages.key !== key;
  const first = pages?.data;
  const extra = more && more.key === key ? more : null;
  const events = [...(first?.events ?? []), ...(extra?.events ?? [])];
  const next = extra ? extra.next : (first?.next ?? null);

  const loadMore = () => {
    if (!next) return;
    getEvents(state.filters, { cursor: next, limit: PAGE })
      .then((p) => setMore({ key, events: [...(extra?.events ?? []), ...p.events], next: p.next }))
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
  };

  return (
    <div className={s.feed}>
      <div className={s.feedHead}>
        <p className={s.feedCount}>
          {loading ? (
            <span className={s.muted}>Loading…</span>
          ) : (
            <>
              <span className="mono">{first?.total ?? 0}</span> {first?.total === 1 ? "event" : "events"}, newest first
            </>
          )}
        </p>
        {API_MOCK && <DemoTag />}
      </div>

      {error ? (
        <div className={s.feedPad} role="alert">
          <EmptyState
            title="The feed didn't load"
            action={
              <Button onClick={() => setAttempt((n) => n + 1)} size="sm">
                Try again
              </Button>
            }
          >
            {error}
          </EmptyState>
        </div>
      ) : loading ? (
        <ul className={s.feedList} aria-busy="true" aria-label="Loading events">
          {Array.from({ length: 6 }, (_, i) => (
            <li key={i} className={s.rowSkeleton} />
          ))}
        </ul>
      ) : events.length === 0 ? (
        <div className={s.feedPad}>
          <EmptyState
            title={EMPTY_TITLE}
            action={
              <Button size="sm" onClick={() => dispatch({ type: "resetFilters" })}>
                {CLEAR_LABEL}
              </Button>
            }
          />
        </div>
      ) : (
        <ul className={s.feedList} onMouseLeave={() => dispatch({ type: "hoverEvent", id: null })}>
          {events.map((e) => {
            const note = pictureNote(e);
            return (
              <li key={e.id}>
                <button
                  className={s.row}
                  aria-current={state.selectedEvent === e.id || undefined}
                  onMouseEnter={() => dispatch({ type: "hoverEvent", id: e.id })}
                  onFocus={() => dispatch({ type: "hoverEvent", id: e.id })}
                  onClick={() => onOpen(e.id)}
                >
                  <Thumb e={e} />
                  <span className={s.rowText}>
                    <span className={`mono ${s.rowType}`}>
                      <CategoryGlyph category={CATEGORY_OF[e.type]} size={9} />
                      {TYPE_LABEL[e.type]} · {SOURCE_LABEL[e.source] ?? e.source}
                    </span>
                    <span className={s.rowTitle}>{e.title}</span>
                    <span className={s.rowMeta}>
                      <span className="mono">{formatAgo(e.observed_at, now)}</span>
                      {note && <span> · {note}</span>}
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
          {next && (
            <li className={s.feedPad}>
              <Button block onClick={loadMore}>
                Show more
              </Button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

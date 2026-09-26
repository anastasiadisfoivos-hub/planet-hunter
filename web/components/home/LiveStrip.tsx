"use client";

// "This week in the sky": counts by category for the last 7 days, the six newest events that have a
// picture, and a plain line for every paused source. Everything comes through lib/api, so in mock mode
// it is the recorded real week, tagged DEMO DATA.

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "@phosphor-icons/react";
import { API_MOCK, clockNow, getEvents, getStatus, type Status } from "@/lib/api";
import { CATEGORIES, type Category, type Image, type SkyEvent } from "@/lib/contract";
import { BASIS_LABEL, CATEGORY_LABEL, DEFAULT_FILTERS, SOURCE_LABEL, TYPE_LABEL, categoryOf } from "@/lib/events";
import { formatAgo, formatDay, formatPercent, formatUtc } from "@/lib/format";
import { imageDisplay } from "@/lib/images";
import { CategoryGlyph } from "@/components/map/CategoryGlyph";
import { DemoTag, EmptyState, Tag } from "@/components/ui";
import s from "./home.module.css";

const NEWEST = 6;
/**
 * Which picture stands for an event on its card, best first: colour pictures, then the survey's
 * difference cutout (the one that shows what changed), then the other cutouts.
 */
const KIND_ORDER: Image["kind"][] = ["sky_context", "solar", "forecast_map", "light_curve", "cutout_difference", "cutout_new", "cutout_reference"];
const CUTOUTS = new Set<Image["kind"]>(["cutout_difference", "cutout_new", "cutout_reference"]);

type Loaded = { now: number; total: number; counts: Record<Category, number>; newest: { event: SkyEvent; image: Image }[] };
type State = { kind: "loading" } | { kind: "error" } | ({ kind: "ready" } & Loaded);

function cardImage(e: SkyEvent): Image | null {
  const withThumb = e.images.filter((i) => i.thumb_url);
  return withThumb.sort((a, b) => KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))[0] ?? null;
}

async function load(signal: AbortSignal): Promise<Loaded> {
  const [now, week, pictured] = await Promise.all([
    clockNow(),
    getEvents(DEFAULT_FILTERS, { limit: 500, signal }),
    getEvents({ ...DEFAULT_FILTERS, withPictures: true }, { limit: 60, signal }),
  ]);
  const counts = Object.fromEntries(Object.keys(CATEGORIES).map((c) => [c, 0])) as Record<Category, number>;
  for (const e of week.events) counts[categoryOf(e.type)]++;
  // Newest first, but events with a colour picture come before ones that only have survey cutouts.
  const withImage = pictured.events
    .map((event) => ({ event, image: cardImage(event) }))
    .filter((x): x is { event: SkyEvent; image: Image } => x.image !== null);
  const newest = [...withImage.filter((x) => !CUTOUTS.has(x.image.kind)), ...withImage.filter((x) => CUTOUTS.has(x.image.kind))]
    .slice(0, NEWEST)
    .sort((a, b) => b.event.observed_at.localeCompare(a.event.observed_at));
  return { now, total: week.total, counts, newest };
}

export function LiveStrip() {
  const [state, setState] = useState<State>({ kind: "loading" });
  const [status, setStatus] = useState<Status | null>(null);

  useEffect(() => {
    const ctl = new AbortController();
    load(ctl.signal).then(
      (d) => setState({ kind: "ready", ...d }),
      () => !ctl.signal.aborted && setState({ kind: "error" }),
    );
    getStatus(ctl.signal).then(setStatus, () => setStatus(null));
    return () => ctl.abort();
  }, []);

  const now = state.kind === "ready" ? state.now : null;
  const paused = (status?.sources ?? [])
    .filter((x) => x.state === "paused" || (!x.is_live && x.state !== "unknown"))
    .sort((a, b) => (a.source === "rubin" ? -1 : b.source === "rubin" ? 1 : 0));

  return (
    <section className={s.live} aria-labelledby="live-title">
      <div className={s.liveHead}>
        <h2 id="live-title" className={s.h2}>
          This week in the sky
        </h2>
        <p className={s.liveMeta}>
          {now !== null ? (
            <>
              Last 7 days, up to <span className="mono">{formatUtc(new Date(now).toISOString())}</span>
            </>
          ) : (
            "Last 7 days"
          )}
          {API_MOCK && <DemoTag />}
        </p>
      </div>

      {paused.length > 0 && now !== null && (
        <ul className={s.paused} aria-label="Paused sources">
          {paused.map((p) => (
            <li key={p.source}>
              <Tag>Paused</Tag>
              <span>
                {SOURCE_LABEL[p.source] ?? p.source} hasn&apos;t sent alerts
                {p.last_event_at ? ` since ${formatDay(p.last_event_at, now)}` : " yet"}.
                {p.source === "rubin" && " Its latest nights are on the map at their real dates."}
              </span>
            </li>
          ))}
        </ul>
      )}

      {state.kind === "error" ? (
        <EmptyState
          title="This week's events didn't load"
          action={
            <Link href="/map" className={s.textLink}>
              Open the sky map <ArrowRight size={14} aria-hidden />
            </Link>
          }
        >
          The events service didn&apos;t answer. The sky map may still have them.
        </EmptyState>
      ) : (
        <>
          <dl className={s.counts} aria-busy={state.kind === "loading"}>
            {(Object.keys(CATEGORIES) as Category[]).map((c) => (
              <div key={c} className={s.count}>
                <dt>
                  <CategoryGlyph category={c} size={11} />
                  {CATEGORY_LABEL[c]}
                </dt>
                <dd className="mono">{state.kind === "ready" ? state.counts[c] : <span className={s.skelNum} />}</dd>
              </div>
            ))}
          </dl>

          <div className={s.newestHead}>
            <h3 className={s.h3}>Newest with pictures</h3>
            <Link href="/map" className={s.textLink}>
              {state.kind === "ready" ? `All ${state.total} on the map` : "Open the sky map"} <ArrowRight size={14} aria-hidden />
            </Link>
          </div>

          {state.kind === "loading" ? (
            <ul className={s.events} aria-hidden>
              {Array.from({ length: NEWEST }, (_, i) => (
                <li key={i} className={s.eventSkel}>
                  <span className={s.eventFrame} />
                  <span className={s.skelLine} />
                  <span className={s.skelLineShort} />
                </li>
              ))}
            </ul>
          ) : state.newest.length === 0 ? (
            <EmptyState title="No pictures this week">Events without pictures are still on the sky map.</EmptyState>
          ) : (
            <ul className={s.events}>
              {state.newest.map(({ event, image }) => (
                <li key={event.id}>
                  <EventCard event={event} image={image} now={state.now} />
                </li>
              ))}
            </ul>
          )}
        </>
      )}
    </section>
  );
}

function EventCard({ event: e, image, now }: { event: SkyEvent; image: Image; now: number }) {
  const d = imageDisplay(image, "row");
  const cutout = CUTOUTS.has(image.kind);
  const tag = d.label ?? (cutout ? "Survey cutout" : null);
  const cat = categoryOf(e.type);
  // The map has no ?event= deep link yet, so the card opens the map itself.
  return (
    <Link href="/map" className={s.eventCard}>
      <span className={s.eventFrame} data-cutout={cutout || undefined}>
        {/* eslint-disable-next-line @next/next/no-img-element -- remote survey thumbnails, as in the map's feed */}
        <img src={d.src} alt={d.alt} loading="lazy" decoding="async" />
        {tag && <Tag className={s.frameTag}>{tag}</Tag>}
      </span>
      <span className={s.eventType}>
        <CategoryGlyph category={cat} size={11} />
        {TYPE_LABEL[e.type]}
      </span>
      <span className={s.eventTitle}>{e.title}</span>
      <span className={s.eventMeta}>
        <span className="mono">{formatAgo(e.observed_at, now)}</span>
        <span>
          <span className="mono">{formatPercent(e.confidence)}</span>, {BASIS_LABEL[e.confidence_basis]}
        </span>
      </span>
      {d.note && <span className={s.eventNote}>{image.kind === "sky_context" ? "Archive photo from years before. The event itself is not in it." : d.note}</span>}
      <span className={s.eventCredit}>{image.credit}</span>
    </Link>
  );
}

"use client";

// Home, "This week": the week's events with pictures, as a bento. The big tile is the newest event with its own
// colour picture (an SDO frame, a Rubin stamp); archive survey cutouts fill the rest. Nine cells, always full.

import Link from "next/link";
import { useEffect, useState } from "react";
import { EventTile } from "@/components/gallery/EventTile";
import { clockNow, getAllEvents } from "@/lib/api";
import type { SkyEvent } from "@/lib/contract";
import { timeWindow } from "@/lib/events";
import { eventPic } from "@/lib/pictures";
import s from "./home.module.css";

const CELLS = 9;

export function pickWeek(events: SkyEvent[], now: number): { count: number; picks: SkyEvent[] } {
  const [since] = timeWindow({ kind: "7d" }, now);
  const week = events.filter((e) => Date.parse(e.observed_at) >= since && Date.parse(e.observed_at) <= now).sort((a, b) => b.observed_at.localeCompare(a.observed_at));
  const withPic = week.filter((e) => eventPic(e.id));
  const own = withPic.find((e) => !eventPic(e.id)!.archive);
  const rest = withPic.filter((e) => e !== own);
  return { count: week.length, picks: (own ? [own, ...rest] : rest).slice(0, CELLS) };
}

export function ThisWeek() {
  const [week, setWeek] = useState<{ count: number; picks: SkyEvent[] } | null>(null);
  useEffect(() => {
    let live = true;
    Promise.all([getAllEvents(), clockNow()]).then(
      ([events, now]) => live && setWeek(pickWeek(events, now)),
      () => live && setWeek({ count: 0, picks: [] }),
    );
    return () => {
      live = false;
    };
  }, []);

  return (
    <section className={`wrap ${s.sec}`} aria-labelledby="week">
      <div className={s.shead}>
        <div>
          <h2 id="week" className={s.h2}>
            This week
          </h2>
          <p className={s.line}>{week ? (week.count ? `${week.count} events in 7 days.` : "Nothing new this week.") : " "}</p>
        </div>
        <Link href="/events" className={s.more}>
          All events →
        </Link>
      </div>
      <div className={s.bento} aria-busy={!week}>
        {week
          ? week.picks.map((e, i) => (
              <EventTile key={e.id} event={e} big={i === 0} className={i === 0 ? s.bigCell : undefined} sizes={i === 0 ? "(max-width: 1023px) 100vw, 656px" : "(max-width: 1023px) 50vw, 320px"} />
            ))
          : Array.from({ length: CELLS }, (_, i) => <div key={i} className={`${s.skeleton} ${i === 0 ? s.bigCell : ""}`} />)}
      </div>
    </section>
  );
}

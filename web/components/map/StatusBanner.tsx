"use client";

import { Info } from "@phosphor-icons/react";
import { DemoTag } from "@/components/ui";
import type { Status } from "@/lib/api";
import { SOURCE_LABEL } from "@/lib/events";
import { formatAgo, formatDay } from "@/lib/format";
import { DISPLAY_SATURATION } from "@/lib/starColor";
import s from "./map.module.css";

/** One line per paused source: "Rubin hasn't sent alerts since 14 Jul." */
export function statusLines(status: Status, now: number): string[] {
  return status.sources
    .filter((x) => !x.is_live)
    .map((x) => {
      const name = SOURCE_LABEL[x.source] ?? x.source;
      return x.last_event_at ? `${name} hasn't sent alerts since ${formatDay(x.last_event_at, now)}.` : `${name} hasn't sent anything yet.`;
    });
}

/** One small button over the sky: "2 sources paused" (or "About the data"); the lines and per-source freshness are in its popover. */
export function StatusBanner({ status, now, demo, footprintUrl }: { status: Status | null; now: number; demo: boolean; footprintUrl: string }) {
  if (!status) return null;
  const lines = statusLines(status, now);
  return (
    <div className={s.status}>
      <button className={s.statusButton} popoverTarget="about-data" type="button">
        <Info size={14} aria-hidden />
        {lines.length ? `${lines.length} ${lines.length === 1 ? "source" : "sources"} paused` : "About the data"}
      </button>
      <div id="about-data" popover="auto" className={s.popover} role="dialog" aria-label="About the data">
        <div className={s.rowBetween}>
          <h2 className={s.h4}>About the data</h2>
          {demo && <DemoTag />}
        </div>
        {lines.length > 0 && <p className={s.statusPopLines}>{lines.join(" ")}</p>}
        {demo && (
          <p className={s.help}>
            Real events recorded up to {formatDay(status.generated_at, now)}, served from a file while the live service is not connected.
          </p>
        )}
        <table className={s.freshness}>
          <thead>
            <tr>
              <th scope="col">Source</th>
              <th scope="col">State</th>
              <th scope="col">Newest event</th>
            </tr>
          </thead>
          <tbody>
            {status.sources.map((x) => (
              <tr key={x.source}>
                <th scope="row">{SOURCE_LABEL[x.source] ?? x.source}</th>
                <td>
                  <span className={s.state} data-live={x.is_live}>
                    {x.is_live ? "Live" : "Paused"}
                  </span>
                </td>
                <td className="mono">{x.last_event_at ? formatAgo(x.last_event_at, now) : "none"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {status.sources
          .filter((x) => x.note)
          .map((x) => (
            <p key={x.source} className={s.help}>
              {x.note}
            </p>
          ))}
        <p className={s.help}>Checked {formatAgo(status.generated_at, now)}. A source counts as live when its newest event is recent enough for that source.</p>
        <details className={s.about}>
          <summary>About this map</summary>
          <p>
            Each event sits at its real position. Events on the Sun sit around the Sun&apos;s position now. Fireballs and geomagnetic storms
            happen at Earth, so they are in the feed but not on the sky.
          </p>
          <p>
            Star colours come from each star&apos;s temperature (B−V for bright stars, the TESS Input Catalog for planet hosts) through{" "}
            <a href="http://www.vendian.org/mncharity/dir3/starcolor/" target="_blank" rel="noreferrer">
              Mitchell Charity&apos;s blackbody table
            </a>
            , with saturation raised {DISPLAY_SATURATION}× so the colours read on black. Stars with no listed temperature are white.
          </p>
          <p>
            Rubin coverage is the survey footprint from Rubin Observatory&apos;s own scheduler (
            <a href={footprintUrl} target="_blank" rel="noreferrer">
              rubin_scheduler
            </a>
            ).
          </p>
        </details>
      </div>
    </div>
  );
}

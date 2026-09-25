"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { CaretRight } from "@phosphor-icons/react";
import { Button, Panel, Segmented } from "@/components/ui";
import { CATEGORIES, type Category, type EventType, type SkyEvent } from "@/lib/contract";
import type { MapData } from "@/lib/data";
import { CATEGORY_LABEL, countBySource, countByType, DEFAULT_FILTERS, isRubinLatest, matches, SOURCE_LABEL, TYPE_LABEL, type TimeRange } from "@/lib/events";
import { formatDay } from "@/lib/format";
import { DISPLAY_SATURATION } from "@/lib/starColor";
import { useStore, type Layers } from "@/state/store";
import { CategoryGlyph } from "./CategoryGlyph";
import s from "./map.module.css";

type TimeKind = TimeRange["kind"];

/** A checkbox that can show "some but not all" (a category with some of its types ticked). */
function TriCheckbox({ checked, mixed, onChange, label }: { checked: boolean; mixed: boolean; onChange: (on: boolean) => void; label: string }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = mixed;
  }, [mixed]);
  return <input ref={ref} type="checkbox" className={s.check} checked={checked} aria-label={label} onChange={(e) => onChange(e.target.checked)} />;
}

function Section({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <section className={s.fSection} aria-label={title}>
      <div className={s.rowBetween}>
        <h3 className="label">{title}</h3>
        {action}
      </div>
      {children}
    </section>
  );
}

function LayerSwitch({ layer, label, children }: { layer: keyof Layers; label: string; children?: ReactNode }) {
  const { state, dispatch } = useStore();
  const on = state.layers[layer];
  return (
    <div className={s.layer}>
      <label className={s.switchRow}>
        <span className={s.layerName}>{label}</span>
        <input type="checkbox" role="switch" className={s.switch} checked={on} onChange={(e) => dispatch({ type: "layer", layer, on: e.target.checked })} />
      </label>
      {on && children && <div className={s.layerBody}>{children}</div>}
    </div>
  );
}

const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/** "14 Jul", or "12 to 14 Jul" when the nights span several days. */
function nightsRange(sorted: string[], now: number): string {
  const a = formatDay(sorted[0], now);
  const b = formatDay(sorted.at(-1)!, now);
  return a === b ? `on ${a}` : `${a} to ${b}`;
}

export function FiltersPanel({ data, events, now }: { data: MapData; events: SkyEvent[]; now: number }) {
  const { state, dispatch } = useStore();
  const f = state.filters;
  const set = (patch: Partial<typeof f>) => dispatch({ type: "filters", patch });
  const byType = countByType(events, f, now);
  const bySource = countBySource(events, f, now);
  const allSources = [...new Set(events.map((e) => e.source))].sort((a, b) => (SOURCE_LABEL[a] ?? a).localeCompare(SOURCE_LABEL[b] ?? b));
  const rubinLatest = events.filter((e) => isRubinLatest(e) && matches(e, { ...f, rubinLatest: true }, now)).length;
  const rubinNights = events.filter(isRubinLatest).map((e) => e.observed_at).sort();
  const changed = JSON.stringify(f) !== JSON.stringify(DEFAULT_FILTERS);

  const setTypes = (types: EventType[], on: boolean) => {
    const next = new Set(f.types);
    for (const t of types) {
      if (on) next.add(t);
      else next.delete(t);
    }
    set({ types: [...next] });
  };

  const setTime = (kind: TimeKind) => {
    if (kind === "custom") set({ time: { kind, start: isoDay(now - 30 * 86400000) + "T00:00:00Z", end: isoDay(now) + "T23:59:59Z" } });
    else set({ time: { kind } });
  };

  const sourceOn = (src: string) => f.sources.length === 0 || f.sources.includes(src);
  const toggleSource = (src: string, on: boolean) => {
    const cur = f.sources.length === 0 ? allSources : f.sources;
    const next = on ? [...new Set([...cur, src])] : cur.filter((x) => x !== src);
    set({ sources: next.length === allSources.length ? [] : next });
  };

  return (
    <Panel
      as="aside"
      title="Filters"
      className={s.filters}
      aria-label="Filters and map layers"
      actions={
        changed && (
          <Button variant="quiet" size="sm" onClick={() => dispatch({ type: "resetFilters" })}>
            Reset
          </Button>
        )
      }
    >
      <div className={s.fStack}>
        <Section title="Time">
          <Segmented<TimeKind>
            label="Time range, by when the event was observed"
            block
            value={f.time.kind}
            onChange={setTime}
            options={[
              { value: "24h", label: "24 h" },
              { value: "7d", label: "7 d" },
              { value: "30d", label: "30 d" },
              { value: "custom", label: "Custom" },
            ]}
          />
          {f.time.kind === "custom" && (
            <div className={s.dateRow}>
              <label className={s.field}>
                <span className="label">From</span>
                <input type="date" value={f.time.start.slice(0, 10)} max={f.time.end.slice(0, 10)} onChange={(e) => e.target.value && f.time.kind === "custom" && set({ time: { ...f.time, start: `${e.target.value}T00:00:00Z` } })} />
              </label>
              <label className={s.field}>
                <span className="label">To</span>
                <input type="date" value={f.time.end.slice(0, 10)} min={f.time.start.slice(0, 10)} onChange={(e) => e.target.value && f.time.kind === "custom" && set({ time: { ...f.time, end: `${e.target.value}T23:59:59Z` } })} />
              </label>
            </div>
          )}
          <p className={s.help}>By when the event was observed, up to {formatDay(new Date(now).toISOString(), now)}.</p>
        </Section>

        <Section title="What">
          <ul className={s.cats}>
            {(Object.keys(CATEGORIES) as Category[]).map((c) => {
              const types = CATEGORIES[c] as readonly EventType[];
              const on = types.filter((t) => f.types.includes(t)).length;
              const n = types.reduce((sum, t) => sum + (f.types.includes(t) ? byType[t] : 0), 0);
              return (
                <li key={c}>
                  <details className={s.cat}>
                    <summary>
                      <TriCheckbox label={CATEGORY_LABEL[c]} checked={on === types.length} mixed={on > 0 && on < types.length} onChange={(v) => setTypes([...types], v)} />
                      <CategoryGlyph category={c} />
                      <span className={s.catName}>{CATEGORY_LABEL[c]}</span>
                      <span className={`mono ${s.count}`}>{n}</span>
                      {types.length > 1 && <CaretRight size={12} className={s.caret} aria-hidden />}
                    </summary>
                    {types.length > 1 && (
                      <ul className={s.types}>
                        {types.map((t) => (
                          <li key={t}>
                            <label className={s.typeRow}>
                              <input type="checkbox" className={s.check} checked={f.types.includes(t)} onChange={(e) => setTypes([t], e.target.checked)} />
                              <span>{TYPE_LABEL[t]}</span>
                              <span className={`mono ${s.count}`}>{byType[t]}</span>
                            </label>
                          </li>
                        ))}
                      </ul>
                    )}
                  </details>
                </li>
              );
            })}
          </ul>
        </Section>

        <Section title="Rubin">
          <label className={s.switchRow}>
            <span className={s.layerName}>Rubin&apos;s latest nights ({rubinNights.length ? ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"][new Date(rubinNights.at(-1)!).getUTCMonth()] : "none"})</span>
            <span className={`mono ${s.count}`}>{rubinLatest}</span>
            <input type="checkbox" role="switch" className={s.switch} checked={f.rubinLatest} onChange={(e) => set({ rubinLatest: e.target.checked })} />
          </label>
          <p className={s.help}>
            Rubin&apos;s alert stream is paused. These are its latest nights with alerts
            {rubinNights.length ? `, ${nightsRange(rubinNights, now)}` : ""}, at their real dates. They are
            older than the time range, so they only show with this switch.
          </p>
        </Section>

        <Section title="Sources">
          <ul className={s.sources}>
            {allSources.map((src) => (
              <li key={src}>
                <label className={s.typeRow}>
                  <input type="checkbox" className={s.check} checked={sourceOn(src)} onChange={(e) => toggleSource(src, e.target.checked)} />
                  <span>{SOURCE_LABEL[src] ?? src}</span>
                  <span className={`mono ${s.count}`}>{bySource[src] ?? 0}</span>
                </label>
              </li>
            ))}
          </ul>
        </Section>

        <Section title="Confidence">
          <label className={s.slider}>
            <span className={s.rowBetween}>
              <span>At least</span>
              <span className="mono">{Math.round(f.minConfidence * 100)}%</span>
            </span>
            <input
              type="range"
              min={0}
              max={100}
              step={5}
              value={Math.round(f.minConfidence * 100)}
              onChange={(e) => set({ minConfidence: Number(e.target.value) / 100 })}
              aria-label="Minimum confidence"
              aria-valuetext={`${Math.round(f.minConfidence * 100)} percent`}
            />
          </label>
          <label className={s.switchRow}>
            <span className={s.layerName}>Only with pictures</span>
            <input type="checkbox" role="switch" className={s.switch} checked={f.withPictures} onChange={(e) => set({ withPictures: e.target.checked })} />
          </label>
        </Section>

        <Section title="Map layers">
          <div className={s.stackTight}>
            <LayerSwitch layer="coverage" label="Rubin coverage">
              <p>Where Rubin&apos;s ten-year survey plans to look.</p>
            </LayerSwitch>
            <LayerSwitch layer="stars" label="Bright stars">
              <p>Naked-eye stars, coloured by temperature, for finding your way.</p>
            </LayerSwitch>
            <LayerSwitch layer="dimStars" label="Dim stars">
              <p>Stars at half brightness, so events stand out.</p>
            </LayerSwitch>
            <LayerSwitch layer="heatmap" label="Rubin alerts heatmap">
              <div className={s.ramp} aria-hidden>
                <span className="mono">0</span>
                <span className={s.rampBar} />
                <span className="mono">{data.heatmap.max}</span>
              </div>
              <p>
                {data.heatmap.total.toLocaleString("en-US")} objects with alerts on the night of {data.heatmap.window ? formatDay(data.heatmap.window.start, now) : "record"}, a recorded
                sample, per sky cell.
              </p>
            </LayerSwitch>
            <LayerSwitch layer="hosts" label="Planet hosts">
              <p>{data.hosts.count.toLocaleString("en-US")} stars with known planets, at their distances in 3D. Pick one to fly to it.</p>
              <Segmented
                label="Star distance scale"
                block
                value={state.trueScale ? "true" : "log"}
                onChange={(v) => dispatch({ type: "trueScale", on: v === "true" })}
                options={[
                  { value: "log", label: "Compressed" },
                  { value: "true", label: "True scale" },
                ]}
              />
            </LayerSwitch>
            <LayerSwitch layer="art" label="Milky Way & nebulae">
              <p>Shapes are illustrations; positions are real.</p>
            </LayerSwitch>
          </div>
        </Section>

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
            <a href={data.footprint.source_url} target="_blank" rel="noreferrer">
              rubin_scheduler
            </a>
            ).
          </p>
        </details>
      </div>
    </Panel>
  );
}

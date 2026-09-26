"use client";

import { useCallback, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { SlidersHorizontal } from "@phosphor-icons/react";
import { Button } from "@/components/ui";
import { CATEGORIES, type Category, type EventType, type SkyEvent } from "@/lib/contract";
import { CATEGORY_LABEL, countBySource, countByType, isRubinLatest, matches, SOURCE_LABEL, TYPE_LABEL, type EventFilters } from "@/lib/events";
import { formatDay } from "@/lib/format";
import { useStore } from "@/state/store";
import { CategoryGlyph } from "./CategoryGlyph";
import { CATEGORY_KEYS, categoryCounts, chipState, isDefault, moreCount, setTypes, toggleCategory } from "./filterModel";
import { Overlay } from "./Overlay";
import { RollingCount } from "./RollingCount";
import s from "./map.module.css";

type Preset = "24h" | "7d" | "30d";
const PRESETS: { value: Preset; label: string }[] = [
  { value: "24h", label: "24 h" },
  { value: "7d", label: "7 d" },
  { value: "30d", label: "30 d" },
];

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
const isoDay = (ms: number) => new Date(ms).toISOString().slice(0, 10);

/**
 * 24 h | 7 d | 30 d as a radio group. A custom range (set in "More") leaves none checked; the first
 * segment then takes the tab stop so the group stays reachable.
 */
function TimeSegments({ value, onChange }: { value: EventFilters["time"]["kind"]; onChange: (v: Preset) => void }) {
  const ref = useRef<HTMLDivElement>(null);
  const current = PRESETS.findIndex((p) => p.value === value);
  const onKey = (e: KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const step = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
    const next = PRESETS[(Math.max(current, 0) + step + PRESETS.length) % PRESETS.length];
    onChange(next.value);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${next.value}"]`)?.focus();
  };
  return (
    <div ref={ref} role="radiogroup" aria-label="Time range, by when the event was observed" className={s.timeSeg} onKeyDown={onKey}>
      {PRESETS.map((p, i) => (
        <button
          key={p.value}
          type="button"
          role="radio"
          data-value={p.value}
          aria-checked={p.value === value}
          tabIndex={i === Math.max(current, 0) ? 0 : -1}
          onClick={() => onChange(p.value)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

function Chip({ category, state, count, onToggle }: { category: Category; state: "on" | "off" | "mixed"; count: number; onToggle: () => void }) {
  return (
    <button
      type="button"
      className={s.chip}
      aria-pressed={state === "on" ? true : state === "mixed" ? "mixed" : false}
      data-empty={count === 0 || undefined}
      aria-label={`${CATEGORY_LABEL[category]}, ${count} ${count === 1 ? "event" : "events"}${state === "mixed" ? ", some types" : ""}`}
      onClick={onToggle}
    >
      <CategoryGlyph category={category} size={11} />
      <span>{CATEGORY_LABEL[category]}</span>
      <RollingCount value={count} className={`mono ${s.chipCount}`} />
    </button>
  );
}

function Group({ title, children, note }: { title: string; children: ReactNode; note?: ReactNode }) {
  return (
    <section className={s.fSection} aria-label={title}>
      <h3 className="label">{title}</h3>
      {children}
      {note}
    </section>
  );
}

function Switch({ label, checked, onChange, count }: { label: ReactNode; checked: boolean; onChange: (on: boolean) => void; count?: number }) {
  return (
    <label className={s.switchRow}>
      <span className={s.layerName}>{label}</span>
      {count !== undefined && <span className={`mono ${s.count}`}>{count}</span>}
      <input type="checkbox" role="switch" className={s.switch} checked={checked} onChange={(e) => onChange(e.target.checked)} />
    </label>
  );
}

/** Everything that is not a time preset or a whole category. */
function MoreFilters({ events, now }: { events: SkyEvent[]; now: number }) {
  const { state, dispatch } = useStore();
  const f = state.filters;
  const set = (patch: Partial<EventFilters>) => dispatch({ type: "filters", patch });
  const byType = countByType(events, f, now);
  const bySource = countBySource(events, f, now);
  const allSources = [...new Set(events.map((e) => e.source))].sort((a, b) => (SOURCE_LABEL[a] ?? a).localeCompare(SOURCE_LABEL[b] ?? b));
  const rubinCount = events.filter((e) => isRubinLatest(e) && matches(e, { ...f, rubinLatest: true }, now)).length;
  const nights = events.filter(isRubinLatest).map((e) => e.observed_at).sort();
  const month = nights.length ? MONTHS[new Date(nights.at(-1)!).getUTCMonth()] : "none";
  const nightsText = nights.length ? (formatDay(nights[0], now) === formatDay(nights.at(-1)!, now) ? formatDay(nights[0], now) : `${formatDay(nights[0], now)} to ${formatDay(nights.at(-1)!, now)}`) : null;

  const sourceOn = (src: string) => f.sources.length === 0 || f.sources.includes(src);
  const toggleSource = (src: string, on: boolean) => {
    const cur = f.sources.length === 0 ? allSources : f.sources;
    const next = on ? [...new Set([...cur, src])] : cur.filter((x) => x !== src);
    set({ sources: next.length === allSources.length ? [] : next });
  };
  const custom = f.time.kind === "custom";

  return (
    <div className={s.fStack}>
      <Group title="Event types">
        <div className={s.typeGroups}>
          {CATEGORY_KEYS.map((c) => (
            <fieldset key={c} className={s.typeGroup}>
              <legend className={s.typeLegend}>
                <CategoryGlyph category={c} size={10} />
                {CATEGORY_LABEL[c]}
              </legend>
              <ul className={s.types}>
                {(CATEGORIES[c] as readonly EventType[]).map((t) => (
                  <li key={t}>
                    <label className={s.typeRow}>
                      <input type="checkbox" className={s.check} checked={f.types.includes(t)} onChange={(e) => set(setTypes(f, [t], e.target.checked))} />
                      <span>{TYPE_LABEL[t]}</span>
                      <span className={`mono ${s.count}`}>{byType[t]}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </fieldset>
          ))}
        </div>
      </Group>

      <Group title="Sources">
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
      </Group>

      <Group title="Quality">
        <label className={s.slider}>
          <span className={s.rowBetween}>
            <span>Minimum confidence</span>
            <span className="mono">{Math.round(f.minConfidence * 100)}%</span>
          </span>
          <input
            type="range"
            min={0}
            max={100}
            step={5}
            value={Math.round(f.minConfidence * 100)}
            onChange={(e) => set({ minConfidence: Number(e.target.value) / 100 })}
            aria-valuetext={`${Math.round(f.minConfidence * 100)} percent`}
          />
        </label>
        <Switch label="Only with pictures" checked={f.withPictures} onChange={(on) => set({ withPictures: on })} />
      </Group>

      <Group title="Dates" note={<p className={s.help}>By when the event was observed. Times are UTC.</p>}>
        <Switch
          label="Custom date range"
          checked={custom}
          onChange={(on) => set({ time: on ? { kind: "custom", start: isoDay(now - 30 * 86400000) + "T00:00:00Z", end: isoDay(now) + "T23:59:59Z" } : { kind: "7d" } })}
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
      </Group>

      <Group title="Rubin" note={<p className={s.help}>Rubin&apos;s alerts are paused; this adds its latest nights{nightsText ? `, ${nightsText},` : ""} at their real dates.</p>}>
        <Switch label={`Rubin's latest nights (${month})`} checked={f.rubinLatest} onChange={(on) => set({ rubinLatest: on })} count={rubinCount} />
      </Group>
    </div>
  );
}

/** Floating filters over the sky: time, the six categories, "More" and Reset. */
export function FilterBar({ events, now }: { events: SkyEvent[]; now: number }) {
  const { state, dispatch } = useStore();
  const f = state.filters;
  const counts = categoryCounts(events, f, now);
  const badge = moreCount(f);
  const [open, setOpen] = useState(false);
  const moreRef = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);

  return (
    <div className={s.filterBar} role="group" aria-label="Filters">
      <div className={s.barScroll}>
        <TimeSegments value={f.time.kind} onChange={(kind) => dispatch({ type: "filters", patch: { time: { kind } } })} />
        <div className={s.chips}>
          {CATEGORY_KEYS.map((c) => (
            <Chip key={c} category={c} state={chipState(f, c)} count={counts[c]} onToggle={() => dispatch({ type: "filters", patch: toggleCategory(f, c) })} />
          ))}
        </div>
      </div>
      <div className={s.barTail}>
        <div className={s.anchor}>
          <button
            ref={moreRef}
            type="button"
            className={s.barButton}
            aria-haspopup="dialog"
            aria-expanded={open}
            aria-controls="more-filters"
            aria-label={badge ? `More filters, ${badge} set` : "More filters"}
            onClick={() => setOpen((o) => !o)}
          >
            <SlidersHorizontal size={14} aria-hidden />
            More
            {badge > 0 && (
              <span className={`mono ${s.badge}`} aria-hidden>
                {badge}
              </span>
            )}
          </button>
          <Overlay id="more-filters" open={open} onClose={close} triggerRef={moreRef} title="More filters" placement="below">
            <MoreFilters events={events} now={now} />
          </Overlay>
        </div>
        {!isDefault(f) && (
          <Button
            variant="quiet"
            size="sm"
            className={s.reset}
            onClick={() => {
              dispatch({ type: "resetFilters" });
              // Reset disappears once pressed; keep keyboard focus in the bar.
              moreRef.current?.focus();
            }}
          >
            Reset
          </Button>
        )}
      </div>
    </div>
  );
}

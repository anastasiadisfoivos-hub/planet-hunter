"use client";

import { useEffect, useState } from "react";
import { Crosshair, Trash, X } from "@phosphor-icons/react";
import { Button, DataGrid, DemoTag, EmptyState, Panel, Segmented, Tag } from "@/components/ui";
import { SPHERE_RADIUS_MAX, SPHERE_RADIUS_MIN, type Forecast } from "@/lib/contract";
import { classify, type HostIndex } from "@/lib/classify";
import { footprintLabel, type MapData } from "@/lib/data";
import { formatCountdown, formatOdds, formatPercent } from "@/lib/odds";
import { capAreaDeg2, formatDec, formatRa, formatRadius } from "@/lib/sky";
import type { ForecastWindow } from "@/lib/mock/forecast";
import { MAX_WATCHES, useStore, type Draft } from "@/state/store";
import { REGION_LABEL, TYPE_LABEL } from "./labels";
import { view } from "./scene/constants";
import s from "./map.module.css";

const LOG_MIN = Math.log10(SPHERE_RADIUS_MIN);
const LOG_MAX = Math.log10(SPHERE_RADIUS_MAX);
const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const nf2 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 2 });
const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function NextVisit({ visits }: { visits: Forecast["visits"] }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, []);
  const next = visits.find((v) => Date.parse(v.time) > now);
  if (!next) return <span className={s.muted}>None planned</span>;
  return (
    <span>
      <span className="mono">{formatCountdown(Date.parse(next.time) - now)}</span>
      <span className={s.muted}> · {next.band} band</span>
    </span>
  );
}

function ago(iso: string, now: number) {
  const min = Math.round((Date.parse(iso) - now) / 60000);
  if (min > -1) return "just now";
  if (min > -60) return rtf.format(min, "minute");
  const h = Math.round(min / 60);
  return h > -24 ? rtf.format(h, "hour") : rtf.format(Math.round(h / 24), "day");
}

function DraftView({
  draft,
  data,
  index,
  forecast,
  onCreate,
  busy,
}: {
  draft: Draft;
  data: MapData;
  index: HostIndex;
  forecast: Forecast | null;
  onCreate: () => void;
  busy: boolean;
}) {
  const { state, dispatch } = useStore();
  const { sphere, result } = draft;
  const region = footprintLabel(data.footprint, sphere.ra_deg, sphere.dec_deg);
  const full = state.watches.length >= MAX_WATCHES;

  const setRadius = (radius_deg: number) => {
    const next = { ...sphere, radius_deg };
    dispatch({ type: "radius", radius_deg, result: classify(next, index, data.footprint) });
  };

  return (
    <div className={s.stack}>
      <div className={s.rowBetween}>
        <div>
          <p className="label">{result.kind === "star" ? "Star watch" : result.kind === "sky" ? "Sky watch" : "Outside Rubin coverage"}</p>
          <h3 className={s.h3}>{result.kind === "star" ? result.name : result.kind === "sky" ? "Patch of sky" : "A sky watch can't go here"}</h3>
        </div>
        <Button variant="quiet" size="sm" icon={<X size={16} />} aria-label="Discard this watch" onClick={() => dispatch({ type: "draft", draft: null })} />
      </div>

      {result.kind === "blocked" && (
        <p className={s.blocked} role="status">
          {result.reason} Draw inside the teal outline instead: that is where Rubin looks.
        </p>
      )}

      <DataGrid
        items={[
          { label: "RA", value: formatRa(sphere.ra_deg), mono: true },
          { label: "Dec", value: formatDec(sphere.dec_deg), mono: true },
          { label: "Radius", value: formatRadius(sphere.radius_deg), mono: true },
          { label: "Area", value: `${nf2.format(capAreaDeg2(sphere.radius_deg))} deg²`, mono: true },
          ...(result.kind === "star"
            ? [
                { label: "TIC", value: String(result.target.tic_id), mono: true },
                { label: "Hosts inside", value: String(result.starsInside), mono: true, hint: result.starsInside > 1 ? "Watching the one nearest the centre" : undefined },
              ]
            : []),
          { label: "Rubin region", value: REGION_LABEL[region] ?? region, wide: true },
        ]}
      />

      <label className={s.slider}>
        <span className={s.rowBetween}>
          <span className="label">Size</span>
          <span className="mono">{formatRadius(sphere.radius_deg)}</span>
        </span>
        <input
          type="range"
          min={LOG_MIN}
          max={LOG_MAX}
          step={0.01}
          value={Math.log10(sphere.radius_deg)}
          onChange={(e) => setRadius(Number((10 ** Number(e.target.value)).toFixed(3)))}
          aria-label="Watch radius"
          aria-valuetext={formatRadius(sphere.radius_deg)}
        />
      </label>

      {result.kind !== "blocked" && (
        <section className={s.stack} aria-label="Forecast">
          <div className={s.rowBetween}>
            <Segmented<ForecastWindow>
              label="Forecast window"
              value={state.window}
              onChange={(value) => dispatch({ type: "window", value })}
              options={[
                { value: "tonight", label: "Tonight" },
                { value: "week", label: "This week" },
              ]}
            />
            <DemoTag />
          </div>
          {forecast ? (
            <>
              <DataGrid
                items={[
                  { label: "Rubin visit chance", value: formatPercent(forecast.rubin_visit_probability), mono: true },
                  { label: "Next Rubin visit", value: <NextVisit visits={forecast.visits} /> },
                ]}
              />
              <div>
                <p className="label">Odds of a detection</p>
                <ul className={s.odds}>
                  {forecast.expected.slice(0, 6).map((e) => (
                    <li key={e.type}>
                      <span>{TYPE_LABEL[e.type]}</span>
                      <span className="mono">{formatOdds(e.mean_count)}</span>
                    </li>
                  ))}
                </ul>
              </div>
              {forecast.known_solar_system_objects.length > 0 && (
                <p className={s.muted}>
                  {forecast.known_solar_system_objects.length} known solar system object
                  {forecast.known_solar_system_objects.length > 1 ? "s" : ""} will cross this patch.
                </p>
              )}
            </>
          ) : (
            <div className={s.skeleton} aria-label="Loading forecast" />
          )}
        </section>
      )}

      <div className={s.actions}>
        <Button variant="primary" onClick={onCreate} disabled={result.kind === "blocked" || draft.dragging || full || busy}>
          {busy ? "Saving…" : "Start watch"}
        </Button>
        {full && <span className={s.muted}>All {MAX_WATCHES} watches are in use. Remove one first.</span>}
      </div>
    </div>
  );
}

function StarView({ i, data, index }: { i: number; data: MapData; index: HostIndex }) {
  const { dispatch } = useStore();
  const h = data.hosts;
  const pc = h.dist[i];
  const watchIt = () => {
    const sphere = { ra_deg: h.ra[i], dec_deg: h.dec[i], radius_deg: 0.25 };
    dispatch({ type: "mode", mode: "draw" });
    dispatch({ type: "draft", draft: { sphere, result: classify(sphere, index, data.footprint), dragging: false } });
  };
  return (
    <div className={s.stack}>
      <div className={s.rowBetween}>
        <div>
          <p className="label">Planet host</p>
          <h3 className={s.h3}>{h.name[i]}</h3>
        </div>
        <Button variant="quiet" size="sm" icon={<X size={16} />} aria-label="Close star details" onClick={() => dispatch({ type: "selectStar", index: null })} />
      </div>
      <DataGrid
        items={[
          { label: "RA", value: formatRa(h.ra[i]), mono: true },
          { label: "Dec", value: formatDec(h.dec[i]), mono: true },
          { label: "Distance", value: `${pc < 10 ? pc.toFixed(1) : nf.format(pc)} pc`, mono: true, hint: `About ${nf.format(pc * 3.2616)} light-years` },
          { label: "Known planets", value: String(h.npl[i]), mono: true },
          { label: "TIC", value: String(h.tic[i]), mono: true },
          { label: "Gaia DR3", value: h.gaia[i] || "Not listed", mono: !!h.gaia[i] },
          { label: "Distance source", value: h.dist_refs[h.ref[i]], wide: true },
        ]}
      />
      <div className={s.actions}>
        <Button variant="primary" onClick={watchIt}>
          Watch this star
        </Button>
      </div>
    </div>
  );
}

export function Inspector({
  data,
  index,
  forecast,
  watchesApi,
}: {
  data: MapData;
  index: HostIndex;
  forecast: Forecast | null;
  watchesApi: { create: (d: Draft) => Promise<void>; remove: (id: string) => Promise<void>; busy: boolean; error: string | null };
}) {
  const { state, dispatch } = useStore();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30_000);
    return () => clearInterval(id);
  }, []);

  return (
    <Panel as="aside" title="New watch" className={s.inspector} aria-label="New watch">
      <div className={s.stack}>
        {state.draft ? (
          <DraftView
            draft={state.draft}
            data={data}
            index={index}
            forecast={forecast}
            busy={watchesApi.busy}
            onCreate={() => state.draft && watchesApi.create(state.draft)}
          />
        ) : state.selectedStar !== null ? (
          <StarView i={state.selectedStar} data={data} index={index} />
        ) : (
          <EmptyState
            title="Draw a watch on the sky"
            action={
              state.mode !== "draw" && (
                <Button icon={<Crosshair size={16} />} onClick={() => dispatch({ type: "mode", mode: "draw" })}>
                  Draw watch
                </Button>
              )
            }
          >
            Drag outward from a point: the further you drag, the larger the patch. A watch on a planet host follows that
            star. A watch on empty sky must sit inside Rubin coverage. Or pick a star to see its details.
          </EmptyState>
        )}

        {watchesApi.error && (
          <p className={s.blocked} role="alert">
            {watchesApi.error}
          </p>
        )}

        <section className={s.watchList} aria-labelledby="watches-h">
          <div className={s.rowBetween}>
            <h3 id="watches-h" className={s.h4}>
              Your watches
            </h3>
            <span className="mono label">
              {state.watches.length}/{MAX_WATCHES}
            </span>
          </div>
          {!state.watchesLoaded ? (
            <div className={s.skeleton} aria-label="Loading watches" />
          ) : state.watches.length === 0 ? (
            <p className={s.muted}>None yet. Explore mode watches never earn points; they are just for looking.</p>
          ) : (
            <ul>
              {state.watches.map((w) => (
                <li key={w.id}>
                  <button
                    className={s.watchRow}
                    onClick={() => view.jumpTo?.(w.sphere.ra_deg, w.sphere.dec_deg, Math.max(3, w.sphere.radius_deg * 8))}
                    aria-label={`Show ${w.kind === "star" ? w.name : "sky watch"} on the map`}
                  >
                    <Tag tone={w.kind === "star" ? "accent" : "neutral"}>{w.kind === "star" ? "Star" : "Sky"}</Tag>
                    <span className={s.watchText}>
                      <span>{w.kind === "star" ? w.name : `${formatRa(w.sphere.ra_deg)} ${formatDec(w.sphere.dec_deg)}`}</span>
                      <span className={`mono ${s.muted}`}>
                        r {formatRadius(w.sphere.radius_deg)} · {ago(w.createdAt, now)}
                      </span>
                    </span>
                  </button>
                  <Button
                    variant="quiet"
                    size="sm"
                    icon={<Trash size={16} />}
                    aria-label={`Remove watch ${w.kind === "star" ? w.name : "on sky patch"}`}
                    onClick={() => watchesApi.remove(w.id)}
                  />
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </Panel>
  );
}

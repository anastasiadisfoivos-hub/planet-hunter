"use client";

import type { ReactNode } from "react";
import { DemoTag, Panel, Segmented } from "@/components/ui";
import { CATCH_TYPES, type CatchType } from "@/lib/contract";
import type { MapData } from "@/lib/data";
import { useStore, type Layers } from "@/state/store";
import { TYPE_LABEL } from "./labels";
import s from "./map.module.css";

const dateFmt = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });

function LayerRow({ layer, label, swatch, children }: { layer: keyof Layers; label: string; swatch?: string; children?: ReactNode }) {
  const { state, dispatch } = useStore();
  const on = state.layers[layer];
  return (
    <div className={s.layer}>
      <label className={s.switchRow}>
        {swatch ? <span className={s.swatch} style={{ background: swatch }} aria-hidden /> : <span className={s.swatchEmpty} aria-hidden />}
        <span className={s.layerName}>{label}</span>
        <input
          type="checkbox"
          role="switch"
          className={s.switch}
          checked={on}
          onChange={(e) => dispatch({ type: "layer", layer, on: e.target.checked })}
        />
      </label>
      {on && children && <div className={s.layerBody}>{children}</div>}
    </div>
  );
}

export function LayersPanel({ data, heatMax }: { data: MapData; heatMax: number }) {
  const { state, dispatch } = useStore();
  const fields = new Set(data.tonight.tiles.map((t) => `${t.ra_deg},${t.dec_deg}`)).size;

  return (
    <Panel as="aside" title="Layers" className={s.layers} aria-label="Map layers">
      <div className={s.stackTight}>
        <LayerRow layer="zone" label="Rubin coverage" swatch="var(--rubin)">
          <p>Where Rubin&apos;s ten-year survey plans to look. Sky watches only work inside it.</p>
        </LayerRow>

        <LayerRow layer="stars" label="Bright stars" swatch="var(--ink-secondary)">
          <p>Naked-eye stars, for finding your way. Planet hosts are always shown, in blue.</p>
        </LayerRow>

        <LayerRow layer="grounds" label="Hunting grounds" swatch="var(--ground-bulge)">
          <ul className={s.legend}>
            <li>
              <span className={s.swatch} style={{ background: "var(--ground-ecliptic)" }} aria-hidden />
              <span>
                <strong>Ecliptic.</strong> Asteroids, near-Earth objects, trans-Neptunian objects, comets.
              </span>
            </li>
            <li>
              <span className={s.swatch} style={{ background: "var(--ground-bulge)" }} aria-hidden />
              <span>
                <strong>Galactic bulge.</strong> Microlensing, flares, variable stars.
              </span>
            </li>
            <li>
              <span className={s.swatch} style={{ background: "var(--ground-high)" }} aria-hidden />
              <span>
                <strong>High galactic latitude.</strong> Supernovae, active galaxies, tidal disruption events.
              </span>
            </li>
          </ul>
        </LayerRow>

        <LayerRow layer="heatmap" label="Detection heatmap" swatch="var(--ink)">
          <label className={s.field}>
            <span className="label">Type</span>
            <select value={state.heatType} onChange={(e) => dispatch({ type: "heatType", value: e.target.value as CatchType | "all" })}>
              <option value="all">All types</option>
              {CATCH_TYPES.map((t) => (
                <option key={t} value={t}>
                  {TYPE_LABEL[t]}
                </option>
              ))}
            </select>
          </label>
          <div className={s.ramp} aria-hidden>
            <span className="mono">0</span>
            <span className={s.rampBar} />
            <span className="mono">{heatMax}</span>
          </div>
          <p>
            Detections per sky cell. Data from {dateFmt.format(new Date(data.heatmap.generated_at))}. <DemoTag />
          </p>
        </LayerRow>

        <LayerRow layer="tonight" label="Rubin tonight" swatch="var(--ink)">
          <p>
            {fields} fields planned for the night of {dateFmt.format(new Date(data.tonight.night))}, each visited twice
            about 33 minutes apart. <DemoTag />
          </p>
        </LayerRow>

        <LayerRow layer="art" label="Artistic nebulae & clouds">
          <p>Shapes are illustrations; positions are real.</p>
        </LayerRow>

        <div className={s.layer}>
          <span className="label">Star distances</span>
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
          <p className={s.muted}>
            {state.trueScale
              ? "Linear. Most hosts crowd close to Earth."
              : "Log scale, so 1.3 pc and 4,300 pc both fit. Directions are always exact."}
          </p>
        </div>

        <details className={s.about}>
          <summary>About this map</summary>
          <p>
            {data.hosts.count.toLocaleString("en-US")} planet hosts from the{" "}
            <a href="https://exoplanetarchive.ipac.caltech.edu/" target="_blank" rel="noreferrer">
              NASA Exoplanet Archive
            </a>{" "}
            inside Rubin coverage. Distances are mostly Gaia DR2 parallax distances, via the TESS Input Catalog.
          </p>
          <p>
            Rubin coverage is the survey footprint from Rubin Observatory&apos;s own scheduler (
            <a href={data.footprint.source_url} target="_blank" rel="noreferrer">
              rubin_scheduler
            </a>{" "}
            {data.footprint.source_version.replace(/^rubin_scheduler /, "").split(",")[0]}).
          </p>
          <p>Nebula and star positions: Sharpless, RCW, Lynds, Green SNR and Yale Bright Star catalogues via VizieR.</p>
        </details>
      </div>
    </Panel>
  );
}

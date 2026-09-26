"use client";

import { useCallback, useRef, useState, type ReactNode } from "react";
import { Stack } from "@phosphor-icons/react";
import { Segmented } from "@/components/ui";
import type { MapData } from "@/lib/data";
import { formatDay } from "@/lib/format";
import { useStore, type Layers } from "@/state/store";
import { Overlay } from "./Overlay";
import s from "./map.module.css";

function LayerSwitch({ layer, label, note }: { layer: keyof Layers; label: string; note?: ReactNode }) {
  const { state, dispatch } = useStore();
  const on = state.layers[layer];
  return (
    <div className={s.layer}>
      <label className={s.switchRow}>
        <span className={s.layerName}>{label}</span>
        <input type="checkbox" role="switch" className={s.switch} checked={on} onChange={(e) => dispatch({ type: "layer", layer, on: e.target.checked })} />
      </label>
      {on && note && <div className={s.layerBody}>{note}</div>}
    </div>
  );
}

/** Map layers, apart from the filters: a button on the sky and a small panel. */
export function LayersControl({ data, now }: { data: MapData; now: number }) {
  const { state, dispatch } = useStore();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLButtonElement>(null);
  const close = useCallback(() => setOpen(false), []);

  return (
    <div className={`${s.anchor} ${s.layersDock}`}>
      <button ref={ref} type="button" className={s.barButton} aria-haspopup="dialog" aria-expanded={open} aria-controls="map-layers" onClick={() => setOpen((o) => !o)}>
        <Stack size={14} aria-hidden />
        Layers
      </button>
      <Overlay id="map-layers" open={open} onClose={close} triggerRef={ref} title="Layers" placement="above">
        <div className={s.fStack}>
          <section className={s.fSection} aria-label="Stars">
            <h3 className="label">Stars</h3>
            <div className={s.stackTight}>
              <LayerSwitch layer="stars" label="Bright stars" note={<p>Naked-eye stars, coloured by temperature, for finding your way.</p>} />
              <LayerSwitch layer="dimStars" label="Dim stars" note={<p>Stars at half brightness, so events stand out.</p>} />
              <LayerSwitch
                layer="hosts"
                label="Planet hosts"
                note={<p>{data.hosts.count.toLocaleString("en-US")} stars with known planets, at their distances in 3D. Pick one to fly to it.</p>}
              />
            </div>
          </section>
          <section className={s.fSection} aria-label="Overlays">
            <h3 className="label">Overlays</h3>
            <div className={s.stackTight}>
              <LayerSwitch layer="coverage" label="Rubin coverage" note={<p>Where Rubin&apos;s ten-year survey plans to look.</p>} />
              <LayerSwitch
                layer="heatmap"
                label="Rubin heatmap"
                note={
                  <>
                    <div className={s.ramp} aria-hidden>
                      <span className="mono">0</span>
                      <span className={s.rampBar} />
                      <span className="mono">{data.heatmap.max}</span>
                    </div>
                    <p>
                      {data.heatmap.total.toLocaleString("en-US")} objects with alerts on the night of{" "}
                      {data.heatmap.window ? formatDay(data.heatmap.window.start, now) : "record"}, a recorded sample, per sky cell.
                    </p>
                  </>
                }
              />
              <LayerSwitch layer="photo" label="Milky Way photograph" note={<p>ESO&apos;s photograph of the whole sky (ESO/S. Brunier, CC BY 4.0).</p>} />
              <LayerSwitch layer="constellations" label="Constellations" note={<p>Faint lines and the names of the major constellations.</p>} />
            </div>
          </section>
          <section className={s.fSection} aria-label="Scale">
            <h3 className="label">Scale</h3>
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
          </section>
        </div>
      </Overlay>
    </div>
  );
}

"use client";

import dynamic from "next/dynamic";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Crosshair, Hand, Stack, Target } from "@phosphor-icons/react";
import { Button, DemoTag, Segmented } from "@/components/ui";
import { indexHosts, type HostIndex } from "@/lib/classify";
import { loadMapData, type MapData } from "@/lib/data";
import { formatRadius } from "@/lib/sky";
import { formatPercent } from "@/lib/odds";
import type { Forecast } from "@/lib/contract";
import { StoreProvider, useStore, type Mode } from "@/state/store";
import { hud, view } from "./scene/constants";
import { Inspector } from "./Inspector";
import { LayersPanel } from "./LayersPanel";
import { useForecast, useWatchesApi } from "./useWatches";
import s from "./map.module.css";

const Scene = dynamic(() => import("./scene/Scene"), { ssr: false, loading: () => null });

const JUMPS: { id: string; label: string; ra: number; dec: number; fov: number }[] = [
  { id: "orion", label: "Orion Nebula", ra: 83.82, dec: -5.39, fov: 6 },
  { id: "carina", label: "Carina Nebula", ra: 161.26, dec: -59.87, fov: 8 },
  { id: "gc", label: "Galactic centre", ra: 266.42, dec: -29.0, fov: 40 },
  { id: "lagoon", label: "Lagoon and Trifid", ra: 270.8, dec: -23.7, fov: 5 },
  { id: "lmc", label: "Large Magellanic Cloud", ra: 80.9, dec: -69.76, fov: 16 },
  { id: "cygnus", label: "Cygnus and the Great Rift", ra: 308, dec: 40, fov: 45 },
];

export default function SkyMapApp() {
  return (
    <StoreProvider>
      <SkyMap />
    </StoreProvider>
  );
}

function SkyMap() {
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let live = true;
    loadMapData()
      .then((d) => live && setData(d))
      .catch((e: unknown) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [attempt]);

  if (error) {
    return (
      <main className={s.shell}>
        <div className={s.centerNote} role="alert">
          <h1 className={s.h3}>The sky map didn&apos;t load</h1>
          <p className={s.muted}>{error}</p>
          <Button
            variant="primary"
            onClick={() => {
              setError(null);
              setAttempt((n) => n + 1);
            }}
          >
            Try again
          </Button>
        </div>
      </main>
    );
  }
  if (!data) {
    return (
      <main className={s.shell} aria-busy="true">
        <div className={`${s.layers} ${s.skeletonPanel}`} aria-hidden />
        <div className={s.sky}>
          <p className={s.centerNote}>Loading the sky…</p>
        </div>
        <div className={`${s.inspector} ${s.skeletonPanel}`} aria-hidden />
        <footer className={s.statusbar} />
      </main>
    );
  }
  return <Loaded data={data} />;
}

/** Compact label beside the watch being drawn: size, kind, and visit chance. */
function Readout({ forecast }: { forecast: Forecast | null }) {
  const { state } = useStore();
  const d = state.draft;
  const ref = useCallback((el: HTMLDivElement | null) => {
    hud.readout = el;
  }, []);
  return (
    <div ref={ref} className={s.readout} data-visible="false" hidden={!d} aria-hidden>
      {d && (
        <>
          <span className="mono">{formatRadius(d.sphere.radius_deg)}</span>
          {d.result.kind === "blocked" ? (
            <span className={s.readoutBlocked}>Outside Rubin coverage</span>
          ) : (
            <>
              <span>{d.result.kind === "star" ? d.result.name : "Sky"}</span>
              {forecast && <span className="mono">{formatPercent(forecast.rubin_visit_probability)} visit</span>}
            </>
          )}
        </>
      )}
    </div>
  );
}

// Only rendered in the browser (data loads client-side), so reading window here is safe.
function Loaded({ data }: { data: MapData }) {
  const { state, dispatch } = useStore();
  const index: HostIndex = useMemo(() => indexHosts(data.hosts), [data.hosts]);
  const [heatMax, setHeatMax] = useState(0);
  const onHeatMax = useCallback((m: number) => setHeatMax(m), []);
  const [sheet, setSheet] = useState<"closed" | "layers" | "watch">("closed");
  const [showFps] = useState(() => new URLSearchParams(window.location.search).has("fps"));
  const watchesApi = useWatchesApi(data);
  const { forecast } = useForecast(state.draft && state.draft.result.kind !== "blocked" ? state.draft.sphere : null, state.window);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      dispatch({ type: "draft", draft: null });
      dispatch({ type: "selectStar", index: null });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dispatch]);

  // Test hook for screenshots and debugging: window.__skymap.jumpTo(ra, dec, fov).
  useEffect(() => {
    (window as unknown as { __skymap: unknown }).__skymap = { jumpTo: (ra: number, dec: number, fov: number) => view.jumpTo?.(ra, dec, fov), view };
  }, []);

  // On phones, open the watch sheet once a drawn watch is released or a star is picked.
  const draftReleased = !!state.draft && !state.draft.dragging;
  const hasStar = state.selectedStar !== null;
  const [autoOpened, setAutoOpened] = useState(false);
  if ((draftReleased || hasStar) && !autoOpened) {
    setAutoOpened(true);
    setSheet("watch");
  }
  if (!draftReleased && !hasStar && autoOpened) setAutoOpened(false);

  const statusRef = (key: "pointer" | "fov" | "fps") => (el: HTMLElement | null) => {
    hud[key] = el;
  };

  const toggle = (tab: "layers" | "watch") => setSheet((cur) => (cur === tab ? "closed" : tab));
  const hint =
    state.mode === "look"
      ? "Drag to look around. Scroll or pinch to zoom. Click a blue star for details."
      : state.draft
        ? null
        : "Drag outward on the sky to draw a watch. A single click draws a 1° watch.";

  return (
    <main className={s.shell} data-mode={state.mode} data-sheet={sheet}>
      <h1 className="sr-only">Planet Hunter sky map</h1>

      <LayersPanel data={data} heatMax={heatMax} />

      <div className={s.sky}>
        <Scene data={data} index={index} showFps={showFps} onHeatMax={onHeatMax} />

        <div className={s.toolbar}>
          <Segmented<Mode>
            label="What dragging does"
            value={state.mode}
            onChange={(mode) => dispatch({ type: "mode", mode })}
            options={[
              { value: "look", label: "Look" },
              { value: "draw", label: "Draw watch" },
            ]}
          />
          <label className={s.jump}>
            <span className="sr-only">Jump to</span>
            <select
              value=""
              onChange={(e) => {
                const j = JUMPS.find((x) => x.id === e.target.value);
                if (j) view.jumpTo?.(j.ra, j.dec, j.fov);
              }}
            >
              <option value="" disabled>
                Jump to…
              </option>
              {JUMPS.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        {hint && <p className={s.hint}>{hint}</p>}
        <Readout forecast={forecast} />
      </div>

      <Inspector data={data} index={index} forecast={forecast} watchesApi={watchesApi} />

      <nav className={s.sheetTabs} aria-label="Panels">
        <button aria-pressed={sheet === "layers"} onClick={() => toggle("layers")}>
          <Stack size={16} aria-hidden />
          Layers
        </button>
        <button aria-pressed={sheet === "watch"} onClick={() => toggle("watch")}>
          <Target size={16} aria-hidden />
          Watch <span className="mono">{state.watches.length}</span>
        </button>
        <button
          aria-pressed={state.mode === "draw"}
          onClick={() => dispatch({ type: "mode", mode: state.mode === "draw" ? "look" : "draw" })}
          aria-label={state.mode === "draw" ? "Switch to look mode" : "Switch to draw mode"}
        >
          {state.mode === "draw" ? <Crosshair size={16} aria-hidden /> : <Hand size={16} aria-hidden />}
          {state.mode === "draw" ? "Drawing" : "Looking"}
        </button>
      </nav>

      <footer className={s.statusbar}>
        <span className={s.statusItem}>
          <span className="label">Pointer</span>
          <span className="mono" ref={statusRef("pointer")}>
            --
          </span>
        </span>
        <span className={s.statusItem}>
          <span className="label">FOV</span>
          <span className="mono" ref={statusRef("fov")}>
            55°
          </span>
        </span>
        <span className={`${s.statusItem} ${s.statusWide}`}>
          <span className="label">Coverage</span>
          <span className="mono">rubin_scheduler {data.footprint.source_version.split(",")[0].replace("rubin_scheduler ", "")}</span>
        </span>
        <span className={`${s.statusItem} ${s.statusWide}`}>
          <span className="label">Hosts</span>
          <span className="mono">{data.hosts.count.toLocaleString("en-US")}</span>
        </span>
        <span className={`${s.statusItem} ${s.statusWide}`}>
          <span className="label">Forecast</span>
          <DemoTag />
        </span>
        {showFps && (
          <span className={s.statusItem}>
            <span className="mono" ref={statusRef("fps")} />
          </span>
        )}
      </footer>
    </main>
  );
}

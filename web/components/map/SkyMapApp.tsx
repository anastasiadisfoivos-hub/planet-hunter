"use client";

import dynamic from "next/dynamic";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Flask, ListBullets, MagnifyingGlass, Star, X } from "@phosphor-icons/react";
import { Button, DemoTag, Panel } from "@/components/ui";
import { API_MOCK, clockNow, getAllEvents, getStatus, type Status } from "@/lib/api";
import type { SkyEvent } from "@/lib/contract";
import { loadMapData, type MapData } from "@/lib/data";
import { applyFilters } from "@/lib/events";
import { indexHosts, type HostIndex } from "@/lib/hosts";
import { eventFov, eventTarget } from "@/lib/markers";
import { starColor } from "@/lib/starColor";
import { StoreProvider, useStore } from "@/state/store";
import { hud, view } from "./scene/constants";
import { EventDetail } from "./EventDetail";
import { Feed } from "./Feed";
import { FilterBar } from "./FilterBar";
import { LayersControl } from "./LayersControl";
import { pauseWhileHidden } from "./motion";
import { RollingCount } from "./RollingCount";
import { StarDetail } from "./StarDetail";
import { StatusBanner } from "./StatusBanner";
import { filtersFromParams, paramsWithFilters } from "./urlFilters";
import s from "./map.module.css";
import lab from "@/components/lab/lab.module.css";

const Scene = dynamic(() => import("./scene/Scene"), { ssr: false, loading: () => null });

const JUMPS: { id: string; label: string; ra: number; dec: number; fov: number }[] = [
  { id: "home", label: "Orion and Taurus", ra: 75, dec: 8, fov: 60 },
  { id: "orion", label: "Orion Nebula", ra: 83.82, dec: -5.39, fov: 6 },
  { id: "carina", label: "Carina Nebula", ra: 161.26, dec: -59.87, fov: 8 },
  { id: "gc", label: "Galactic centre", ra: 266.42, dec: -29.0, fov: 40 },
  { id: "lmc", label: "Large Magellanic Cloud", ra: 80.9, dec: -69.76, fov: 16 },
  { id: "cygnus", label: "Cygnus", ra: 308, dec: 40, fov: 45 },
];

type Loaded = { map: MapData; events: SkyEvent[]; now: number };

export default function SkyMapApp() {
  return (
    <StoreProvider>
      <SkyMap />
    </StoreProvider>
  );
}

function SkyMap() {
  const { dispatch } = useStore();
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  // Filters from a shared link, applied before the map and the feed first render.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    dispatch({ type: "filters", patch: filtersFromParams(params) });
  }, [dispatch]);

  useEffect(() => {
    let live = true;
    Promise.all([loadMapData(), getAllEvents(), clockNow()])
      .then(([map, events, now]) => live && setLoaded({ map, events, now }))
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
  if (!loaded) {
    return (
      <main className={s.shell} aria-busy="true">
        <div className={s.sky}>
          <p className={s.centerNote}>Loading the sky…</p>
        </div>
        <div className={`${s.side} ${s.skeletonPanel}`} aria-hidden />
        <footer className={s.statusbar} />
      </main>
    );
  }
  return <MapView {...loaded} />;
}

/** Key facts for a planet host in close-up. The surface is procedural; the numbers are catalogue values. */
function StarHud({ data, i }: { data: MapData; i: number }) {
  const h = data.hosts;
  const teff = h.teff[i];
  const rad = h.rad?.[i] ?? 0;
  const pc = h.dist[i];
  const nf = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
  const [r, g, b] = starColor(teff).map((v) => Math.round(v * 255));
  return (
    <section className={s.starHud} aria-label={`${h.name[i]} close-up`}>
      <p className="label">Planet host</p>
      <h2 className={s.starHudName}>{h.name[i]}</h2>
      <dl className={s.starHudFacts}>
        <div>
          <dt className="label">Temperature</dt>
          <dd className="mono">
            <span className={s.starSwatch} style={{ background: `rgb(${r} ${g} ${b})` }} aria-hidden />
            {teff > 0 ? `${nf.format(teff)} K` : "Not listed"}
          </dd>
        </div>
        <div>
          <dt className="label">Radius</dt>
          <dd className="mono">{rad > 0 ? `${rad < 1 ? rad.toFixed(2) : rad.toFixed(1)} R☉` : "Not listed"}</dd>
        </div>
        <div>
          <dt className="label">Distance</dt>
          <dd className="mono">
            {pc < 10 ? pc.toFixed(2) : nf.format(pc)} pc<span className={s.muted}> · {nf.format(pc * 3.2616)} ly</span>
          </dd>
        </div>
      </dl>
      <p className={s.starHudNote}>
        Surface is an illustration; colour, size and position are from real data.
        {rad > 0 ? "" : " No radius is listed, so it is drawn at the Sun's size."}
      </p>
    </section>
  );
}

/** DOM labels the scene positions each frame. */
function Labels() {
  const ref = (key: "hover" | "earth" | "sun") => (el: HTMLElement | null) => {
    hud[key] = el;
  };
  return (
    <>
      <div ref={ref("hover")} className={s.hoverLabel} data-visible="false" aria-hidden />
      <div ref={ref("earth")} className={s.landmark} data-visible="false" aria-hidden>
        Earth
      </div>
      <div ref={ref("sun")} className={s.landmark} data-visible="false" aria-hidden>
        Sun
      </div>
    </>
  );
}

type Sheet = "closed" | "feed";

function MapView({ map, events, now }: Loaded) {
  const { state, dispatch } = useStore();
  const index: HostIndex = useMemo(() => indexHosts(map.hosts), [map.hosts]);
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const [showFps] = useState(() => params.has("fps"));
  const [status, setStatus] = useState<Status | null>(null);
  const [sheet, setSheet] = useState<Sheet>("closed");
  const shown = useMemo(() => applyFilters(events, state.filters, now), [events, state.filters, now]);
  const selected = useMemo(() => events.find((e) => e.id === state.selectedEvent) ?? null, [events, state.selectedEvent]);

  useEffect(() => {
    const ctl = new AbortController();
    getStatus(ctl.signal)
      .then(setStatus)
      .catch(() => setStatus(null));
    return () => ctl.abort();
  }, []);

  // DESIGN.md: animation pauses while the tab is hidden (the 3D loop stops itself; this covers CSS and FLIP).
  useEffect(() => pauseWhileHidden(), []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented || document.querySelector(":popover-open")) return;
      dispatch({ type: "selectEvent", id: null });
      dispatch({ type: "selectStar", star: null });
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [dispatch]);

  // Deep link from the Lab: /map?host=<TIC> or /map?bright=<sky-objects index> flies to that star once the scene is ready.
  useEffect(() => {
    const tic = Number(params.get("host"));
    const b = params.has("bright") ? Number(params.get("bright")) : -1;
    const hi = tic > 0 ? map.hosts.tic.indexOf(tic) : -1;
    const target = hi >= 0 ? ({ kind: "host", i: hi } as const) : b >= 0 && b < map.sky.stars.ra.length ? ({ kind: "bright", i: b } as const) : null;
    if (!target) return;
    let raf = 0;
    let frames = 0;
    const wait = () => {
      // A few frames after the camera exists, so host positions are laid out and the flight is visible.
      if (view.jumpTo && ++frames > 10) {
        dispatch({ type: "layer", layer: target.kind === "host" ? "hosts" : "stars", on: true });
        dispatch({ type: "selectStar", star: target });
      } else raf = requestAnimationFrame(wait);
    };
    raf = requestAnimationFrame(wait);
    return () => cancelAnimationFrame(raf);
  }, [params, map, dispatch]);

  // Keep the address bar in step with the filters, so the view can be shared. replaceState: filter
  // changes are not pages, so Back still leaves the map.
  useEffect(() => {
    const cur = new URLSearchParams(window.location.search);
    const next = paramsWithFilters(state.filters, cur);
    if (next.toString() === cur.toString()) return;
    // Commas are legal in a query string; keep shared links readable.
    const q = next.toString().replace(/%2C/g, ",");
    window.history.replaceState(window.history.state, "", `${window.location.pathname}${q ? `?${q}` : ""}${window.location.hash}`);
  }, [state.filters]);

  // Test hook for screenshots and debugging.
  useEffect(() => {
    (window as unknown as { __skymap: unknown }).__skymap = {
      jumpTo: (ra: number, dec: number, fov: number) => view.jumpTo?.(ra, dec, fov),
      selectEvent: (id: string | null) => dispatch({ type: "selectEvent", id }),
      filters: (patch: object) => dispatch({ type: "filters", patch }),
      layer: (layer: string, on: boolean) => dispatch({ type: "layer", layer: layer as never, on }),
      select: (i: number | null, kind: "host" | "bright" = "host") => dispatch({ type: "selectStar", star: i === null ? null : { kind, i } }),
      view,
    };
  }, [dispatch]);

  const open = useCallback(
    (id: string) => {
      dispatch({ type: "selectEvent", id });
      setSheet("feed");
    },
    [dispatch],
  );

  const showOnMap = useCallback(
    (e: SkyEvent) => {
      const t = eventTarget(e, now);
      if (!t) return;
      view.jumpTo?.(t.ra, t.dec, eventFov(e));
      // On a phone the detail covers the map: close it so the flight is visible. The marker stays selected.
      setSheet("closed");
    },
    [now],
  );

  // Picking a marker or a star on the map opens its panel (on a phone, as a full sheet).
  const selKey = state.selectedEvent ?? (state.selectedStar ? `${state.selectedStar.kind}:${state.selectedStar.i}` : null);
  const [seen, setSeen] = useState<string | null>(null);
  if (selKey !== seen) {
    setSeen(selKey);
    if (selKey) setSheet("feed");
  }

  const statusRef = (key: "pointer" | "fov" | "fps") => (el: HTMLElement | null) => {
    hud[key] = el;
  };
  const hostHud = state.selectedStar?.kind === "host" && state.layers.hosts;
  const star = state.selectedStar;
  const starsOff = !state.layers.stars && !state.layers.hosts;

  return (
    <main className={s.shell} data-sheet={sheet} data-detail={selected || star ? "open" : "closed"}>
      <h1 className="sr-only">Sky events map</h1>

      <div className={s.sky}>
        <Scene data={map} index={index} events={shown} now={now} showFps={showFps} noDetail={params.has("nodetail")} />

        <FilterBar events={events} now={now} />
        <LayersControl data={map} now={now} />

        <div className={s.utilities}>
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
          <StatusBanner status={status} now={now} demo={API_MOCK} footprintUrl={map.footprint.source_url} />
          <Link href="/lab" className={lab.mapLab}>
            <Flask size={14} aria-hidden />
            <span className={s.linkText}>Lab</span>
          </Link>
          <Link href="/finder" className={lab.mapLab}>
            <MagnifyingGlass size={14} aria-hidden />
            <span className={s.linkText}>Finder</span>
          </Link>
        </div>

        {hostHud && <StarHud data={map} i={state.selectedStar!.i} />}
        {starsOff && (
          <div className={s.starsOff} role="status">
            <span>All star layers are off</span>
            <Button
              size="sm"
              icon={<Star size={14} />}
              onClick={() => {
                dispatch({ type: "layer", layer: "stars", on: true });
                dispatch({ type: "layer", layer: "hosts", on: true });
              }}
            >
              Show stars
            </Button>
          </div>
        )}
        <Labels />
      </div>

      <Panel
        key={selected ? `event:${selected.id}` : star ? `star:${star.kind}:${star.i}` : "feed"}
        as="aside"
        className={s.side}
        aria-label={selected ? "Event details" : star ? "Star details" : "Feed"}
        title={selected || star ? undefined : "Feed"}
        actions={
          selected || star ? undefined : (
            <Button variant="quiet" size="sm" className={s.sheetClose} icon={<X size={16} />} aria-label="Close feed" onClick={() => setSheet("closed")} />
          )
        }
        flush
      >
        {selected ? (
          <EventDetail
            event={selected}
            now={now}
            onBack={() => {
              dispatch({ type: "selectEvent", id: null });
            }}
            onShow={showOnMap}
          />
        ) : star ? (
          <StarDetail data={map} star={star} onBack={() => dispatch({ type: "selectStar", star: null })} />
        ) : (
          <Feed now={now} onOpen={open} />
        )}
      </Panel>

      <nav className={s.sheetTabs} aria-label="Panels">
        <button aria-pressed={sheet === "feed"} onClick={() => setSheet((cur) => (cur === "feed" ? "closed" : "feed"))}>
          <ListBullets size={16} aria-hidden />
          Feed <RollingCount value={shown.length} className="mono" />
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
            60°
          </span>
        </span>
        <span className={s.statusItem}>
          <span className="label">Showing</span>
          <span className="mono">
            <RollingCount value={shown.length} /> {shown.length === 1 ? "event" : "events"}
          </span>
        </span>
        {API_MOCK && (
          <span className={`${s.statusItem} ${s.statusWide}`}>
            <span className="label">Data</span>
            <DemoTag />
          </span>
        )}
        {showFps && (
          <span className={s.statusItem}>
            <span className="mono" ref={statusRef("fps")} />
          </span>
        )}
      </footer>
    </main>
  );
}

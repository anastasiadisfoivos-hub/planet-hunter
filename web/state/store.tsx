"use client";

import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import { DEFAULT_FILTERS, type EventFilters } from "@/lib/events";

export type Layers = {
  /** Rubin's survey footprint, a subtle overlay. */
  coverage: boolean;
  /** Yale Bright Star Catalogue, for orientation. */
  stars: boolean;
  /** Stars at half brightness, so event markers are the brightest things on screen. */
  dimStars: boolean;
  /** Known planet hosts, at their distances in 3D. Every star is clickable and can be analyzed. */
  hosts: boolean;
  /** One recorded night of Rubin alerts, binned on the sky. */
  heatmap: boolean;
  /** Procedural Milky Way and nebulae. */
  art: boolean;
};

/** A selected star: a planet host (hosts.json index) or a bright catalogue star (sky-objects index). */
export type StarRef = { kind: "host" | "bright"; i: number };

export type State = {
  layers: Layers;
  trueScale: boolean;
  filters: EventFilters;
  /** The event in the detail panel. */
  selectedEvent: string | null;
  /** The event whose feed row is under the pointer (its marker is highlighted). */
  hoverEvent: string | null;
  /** The star in the star panel. A planet host also gets the 3D close-up. */
  selectedStar: StarRef | null;
};

export type Action =
  | { type: "layer"; layer: keyof Layers; on: boolean }
  | { type: "trueScale"; on: boolean }
  | { type: "filters"; patch: Partial<EventFilters> }
  | { type: "resetFilters" }
  | { type: "selectEvent"; id: string | null }
  | { type: "hoverEvent"; id: string | null }
  | { type: "selectStar"; star: StarRef | null };

export const initialState: State = {
  layers: { coverage: true, stars: true, dimStars: true, hosts: true, heatmap: false, art: false },
  trueScale: false,
  filters: DEFAULT_FILTERS,
  selectedEvent: null,
  hoverEvent: null,
  selectedStar: null,
};

export function reducer(state: State, a: Action): State {
  switch (a.type) {
    case "layer": {
      const layers = { ...state.layers, [a.layer]: a.on };
      // Hiding a star layer closes a star selected from it.
      const hidden = !a.on && ((a.layer === "hosts" && state.selectedStar?.kind === "host") || (a.layer === "stars" && state.selectedStar?.kind === "bright"));
      return { ...state, layers, selectedStar: hidden ? null : state.selectedStar };
    }
    case "trueScale":
      return { ...state, trueScale: a.on };
    case "filters":
      return { ...state, filters: { ...state.filters, ...a.patch } };
    case "resetFilters":
      return { ...state, filters: DEFAULT_FILTERS };
    case "selectEvent":
      return { ...state, selectedEvent: a.id, selectedStar: a.id ? null : state.selectedStar };
    case "hoverEvent":
      return state.hoverEvent === a.id ? state : { ...state, hoverEvent: a.id };
    case "selectStar":
      return { ...state, selectedStar: a.star, selectedEvent: a.star !== null ? null : state.selectedEvent };
  }
}

const Ctx = createContext<{ state: State; dispatch: Dispatch<Action> } | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initialState);
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export function useStore() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStore outside StoreProvider");
  return v;
}

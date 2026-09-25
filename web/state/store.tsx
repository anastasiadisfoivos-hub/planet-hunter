"use client";

import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import { DEFAULT_FILTERS, type EventFilters } from "@/lib/events";

export type Layers = {
  /** Rubin's survey footprint, a subtle overlay. */
  coverage: boolean;
  /** Yale Bright Star Catalogue, for orientation. */
  stars: boolean;
  /** Known planet hosts in 3D (off by default; a decision about this layer is pending). */
  hosts: boolean;
  /** One recorded night of Rubin alerts, binned on the sky. */
  heatmap: boolean;
  /** Procedural Milky Way and nebulae. */
  art: boolean;
};

export type State = {
  layers: Layers;
  trueScale: boolean;
  filters: EventFilters;
  /** The event in the detail panel. */
  selectedEvent: string | null;
  /** The event whose feed row is under the pointer (its marker is highlighted). */
  hoverEvent: string | null;
  /** A planet host in close-up (only with the hosts layer on). */
  selectedStar: number | null;
};

export type Action =
  | { type: "layer"; layer: keyof Layers; on: boolean }
  | { type: "trueScale"; on: boolean }
  | { type: "filters"; patch: Partial<EventFilters> }
  | { type: "resetFilters" }
  | { type: "selectEvent"; id: string | null }
  | { type: "hoverEvent"; id: string | null }
  | { type: "selectStar"; index: number | null };

export const initialState: State = {
  layers: { coverage: true, stars: true, hosts: false, heatmap: false, art: false },
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
      // Hiding the hosts ends any host close-up.
      return { ...state, layers, selectedStar: a.layer === "hosts" && !a.on ? null : state.selectedStar };
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
      return { ...state, selectedStar: a.index, selectedEvent: a.index !== null ? null : state.selectedEvent };
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

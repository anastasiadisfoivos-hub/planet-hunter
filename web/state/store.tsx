"use client";

import { createContext, useContext, useReducer, type Dispatch, type ReactNode } from "react";
import type { CatchType, Sphere, StarTarget } from "@/lib/contract";
import type { ForecastWindow } from "@/lib/mock/forecast";

/** What dragging on the sky does. */
export type Mode = "look" | "draw";

/** What a drawn sphere turns into. */
export type DraftResult =
  | { kind: "star"; target: StarTarget; hostIndex: number; name: string; starsInside: number }
  | { kind: "sky" }
  | { kind: "blocked"; reason: string };

export type Draft = { sphere: Sphere; result: DraftResult; dragging: boolean };

/** A watch as the map shows it (built from an api Trap). */
export type Watch = {
  id: string;
  sphere: Sphere;
  createdAt: string;
} & ({ kind: "star"; target: StarTarget; name: string } | { kind: "sky" });

export type Layers = {
  zone: boolean;
  grounds: boolean;
  heatmap: boolean;
  tonight: boolean;
  art: boolean;
  stars: boolean;
};

export type State = {
  mode: Mode;
  layers: Layers;
  heatType: CatchType | "all";
  trueScale: boolean;
  window: ForecastWindow;
  draft: Draft | null;
  watches: Watch[];
  watchesLoaded: boolean;
  selectedStar: number | null;
};

export type Action =
  | { type: "mode"; mode: Mode }
  | { type: "layer"; layer: keyof Layers; on: boolean }
  | { type: "heatType"; value: CatchType | "all" }
  | { type: "trueScale"; on: boolean }
  | { type: "window"; value: ForecastWindow }
  | { type: "draft"; draft: Draft | null }
  | { type: "radius"; radius_deg: number; result: DraftResult }
  | { type: "watches"; watches: Watch[] }
  | { type: "watchAdded"; watch: Watch }
  | { type: "watchRemoved"; id: string }
  | { type: "selectStar"; index: number | null };

const initial: State = {
  mode: "look",
  layers: { zone: true, grounds: false, heatmap: false, tonight: false, art: false, stars: true },
  heatType: "all",
  trueScale: false,
  window: "tonight",
  draft: null,
  watches: [],
  watchesLoaded: false,
  selectedStar: null,
};

export const MAX_WATCHES = 8;

function reducer(state: State, a: Action): State {
  switch (a.type) {
    case "mode":
      return { ...state, mode: a.mode, draft: a.mode === "look" ? null : state.draft };
    case "layer":
      return { ...state, layers: { ...state.layers, [a.layer]: a.on } };
    case "heatType":
      return { ...state, heatType: a.value };
    case "trueScale":
      return { ...state, trueScale: a.on };
    case "window":
      return { ...state, window: a.value };
    case "draft":
      return { ...state, draft: a.draft, selectedStar: a.draft ? null : state.selectedStar };
    case "radius":
      if (!state.draft) return state;
      return { ...state, draft: { ...state.draft, sphere: { ...state.draft.sphere, radius_deg: a.radius_deg }, result: a.result } };
    case "watches":
      return { ...state, watches: a.watches.slice(0, MAX_WATCHES), watchesLoaded: true };
    case "watchAdded":
      return { ...state, watches: [...state.watches, a.watch], draft: null };
    case "watchRemoved":
      return { ...state, watches: state.watches.filter((w) => w.id !== a.id) };
    case "selectStar":
      return { ...state, selectedStar: a.index, draft: a.index !== null ? null : state.draft };
  }
}

const Ctx = createContext<{ state: State; dispatch: Dispatch<Action> } | null>(null);

export function StoreProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, initial);
  return <Ctx.Provider value={{ state, dispatch }}>{children}</Ctx.Provider>;
}

export function useStore() {
  const v = useContext(Ctx);
  if (!v) throw new Error("useStore outside StoreProvider");
  return v;
}

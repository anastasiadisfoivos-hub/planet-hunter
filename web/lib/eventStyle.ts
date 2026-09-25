// How each category is drawn: colour AND shape, so the map never relies on colour alone.
// Colours are tokens in app/tokens.css (--cat-*); the shapes are drawn by the marker shader and,
// for legends and feed rows, by CSS (components/map/CategoryGlyph.tsx).

import type { Category } from "./contract";

export type MarkerShape = "ring" | "diamond" | "square" | "triangle" | "plus" | "dot";

export const CATEGORY_STYLE: Record<Category, { token: string; fallback: string; shape: MarkerShape }> = {
  transients: { token: "--cat-transient", fallback: "#e8836a", shape: "ring" },
  solar_system: { token: "--cat-solar-system", fallback: "#8fd18a", shape: "diamond" },
  sun_space_weather: { token: "--cat-sun", fallback: "#f2c14e", shape: "square" },
  earth_atmosphere: { token: "--cat-earth", fallback: "#7cc4f2", shape: "triangle" },
  high_energy: { token: "--cat-high-energy", fallback: "#d98bd8", shape: "plus" },
  other: { token: "--cat-other", fallback: "#a1a6b0", shape: "dot" },
};

/** Shape index for the marker shader. */
export const SHAPE_INDEX: Record<MarkerShape, number> = { ring: 0, diamond: 1, square: 2, triangle: 3, plus: 4, dot: 5 };

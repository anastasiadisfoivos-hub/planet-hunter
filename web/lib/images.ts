// How an event image is shown. One place for the rules, so feed rows and the detail panel agree:
//   - rows use thumb_url (falling back to url); the detail panel uses url;
//   - survey cutouts are tiny (30 to 63 px): pixelated, at 4x under 48 px and 3x otherwise;
//   - forecast maps are labelled as forecasts, never as photos;
//   - sky-context images show the spot years before the event, so their source caption is always visible.

import type { Image } from "./contract.ts";

export type ImageVariant = "row" | "detail";

export type ImageDisplay = {
  src: string;
  alt: string;
  /** Crisp pixel scaling (`image-rendering: pixelated`). */
  pixelated: boolean;
  /** Integer upscale for cutouts; null when the image scales to fit. */
  scale: number | null;
  /** Rendered width in CSS px when known up front (cutouts with a listed size). */
  width: number | null;
  height: number | null;
  /** Short tag shown on the image, e.g. "Forecast". */
  label: string | null;
  /** A plain-language note shown with the caption. */
  note: string | null;
  caption: string;
  /** True when the caption must never be hidden or truncated away. */
  captionAlwaysVisible: boolean;
};

const CUTOUTS = new Set<Image["kind"]>(["cutout_reference", "cutout_new", "cutout_difference"]);

/** Upscale factor for a cutout of `px` pixels: 4x for the smallest, 3x for the rest. */
export function cutoutScale(px: number | null): number {
  return px !== null && px < 48 ? 4 : 3;
}

export function imageDisplay(img: Image, variant: ImageVariant): ImageDisplay {
  const cutout = CUTOUTS.has(img.kind);
  const scale = cutout ? cutoutScale(img.width) : null;
  const forecast = img.kind === "forecast_map";
  const context = img.kind === "sky_context";
  return {
    src: variant === "row" ? (img.thumb_url ?? img.url) : img.url,
    alt: img.caption,
    pixelated: cutout,
    scale,
    width: cutout && img.width !== null ? img.width * scale! : null,
    height: cutout && img.height !== null ? img.height * scale! : null,
    label: forecast ? "Forecast" : null,
    note: forecast ? "Model forecast map, not a photo." : context ? "Archive photo, taken years before this event. The event itself is not in it." : null,
    caption: img.caption,
    captionAlwaysVisible: context,
  };
}

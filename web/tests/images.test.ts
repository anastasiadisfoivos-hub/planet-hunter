import { test } from "node:test";
import assert from "node:assert/strict";
import { imageDisplay } from "../lib/images.ts";
import type { Image } from "../lib/contract.ts";

const img = (over: Partial<Image>): Image => ({
  url: "https://x/full.png",
  thumb_url: "https://x/thumb.png",
  kind: "cutout_new",
  caption: "Rubin new image, 2026-09-24",
  credit: "Rubin/Fink",
  license: "CC BY 4.0",
  width: 63,
  height: 63,
  ...over,
});

test("feed rows use thumb_url, the detail panel uses url", () => {
  assert.equal(imageDisplay(img({}), "row").src, "https://x/thumb.png");
  assert.equal(imageDisplay(img({}), "detail").src, "https://x/full.png");
});

test("rows fall back to url when there is no thumbnail", () => {
  assert.equal(imageDisplay(img({ thumb_url: null }), "row").src, "https://x/full.png");
});

test("survey cutouts render pixelated at 3 to 4 times their size", () => {
  const small = imageDisplay(img({ width: 30, height: 30 }), "detail");
  assert.equal(small.pixelated, true);
  assert.equal(small.width, 120);
  const big = imageDisplay(img({ kind: "cutout_difference", width: 63, height: 63 }), "detail");
  assert.equal(big.width, 189);
  assert.equal(imageDisplay(img({ kind: "sky_context", width: 600 }), "detail").pixelated, false);
});

test("cutouts with unknown size still render pixelated, sized after load", () => {
  const d = imageDisplay(img({ width: null, height: null }), "detail");
  assert.equal(d.pixelated, true);
  assert.equal(d.width, null);
});

test("forecast maps are labelled as forecasts, not photos", () => {
  const d = imageDisplay(img({ kind: "forecast_map", caption: "NOAA OVATION aurora forecast" }), "row");
  assert.equal(d.label, "Forecast");
  assert.match(d.note ?? "", /not a photo/i);
});

test("sky context keeps its source caption visible, even in a feed row", () => {
  const cap = "Legacy Survey DR10, taken 2019: before this event";
  const row = imageDisplay(img({ kind: "sky_context", caption: cap }), "row");
  assert.equal(row.caption, cap);
  assert.equal(row.captionAlwaysVisible, true);
  assert.equal(imageDisplay(img({}), "row").captionAlwaysVisible, false);
});

test("alt text is the caption", () => {
  assert.equal(imageDisplay(img({}), "row").alt, "Rubin new image, 2026-09-24");
});

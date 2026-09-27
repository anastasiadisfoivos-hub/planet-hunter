// Candidate rows: a click opens that row's dossier and nothing else (the old stretched ::after link covered the page).
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { rowClickTarget } from "../../components/finder/finder.ts";

const at = (closestHit: boolean, mods: Partial<{ metaKey: boolean; ctrlKey: boolean; shiftKey: boolean; button: number }> = {}) => ({
  target: { closest: () => (closestHit ? {} : null) } as unknown as EventTarget,
  metaKey: false,
  ctrlKey: false,
  shiftKey: false,
  button: 0,
  ...mods,
});

test("a row click opens its dossier; links, selections, other buttons and modified clicks behave as expected", () => {
  assert.equal(rowClickTarget(at(false), ""), "open");
  assert.equal(rowClickTarget(at(true), ""), "ignore", "a click on the name link is the link's own");
  assert.equal(rowClickTarget(at(false), "TIC 7520"), "ignore", "selecting text does not navigate");
  assert.equal(rowClickTarget(at(false, { metaKey: true }), ""), "new-tab");
  assert.equal(rowClickTarget(at(false, { button: 1 }), ""), "ignore");
});

test("no stretched-link overlays: nothing in the new site's styles covers its container with ::after + inset 0", () => {
  for (const f of ["components/finder/finder.module.css", "components/monitor/log.module.css", "components/shell/shell.module.css"]) {
    const css = readFileSync(new URL(`../../${f}`, import.meta.url), "utf8");
    const overlays = [...css.matchAll(/::after\s*\{[^}]*inset:\s*0/g)];
    assert.equal(overlays.length, 0, `${f} has a stretched ::after overlay`);
  }
});

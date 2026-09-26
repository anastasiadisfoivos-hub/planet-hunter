// A tiny binned fold per demo candidate (48 points: hours from mid-dip and median flux), so lists can draw the dip
// without downloading each candidate's full light curve. Mock data only: the live API would serve these itself.
//
//   node scripts/build-finder-folds.mjs  →  public/data/finder/folds.mock.json

import { readFileSync, readdirSync, writeFileSync } from "node:fs";

const dir = new URL("../public/data/finder/c/", import.meta.url);
const out = {};
for (const f of readdirSync(dir)) {
  if (!f.endsWith(".json")) continue;
  const { candidate: c } = JSON.parse(readFileSync(new URL(f, dir), "utf8"));
  const P = c.period_d * 24;
  const bins = new Map();
  c.folded.phase.forEach((p, i) => {
    const h = p * P;
    if (Math.abs(h) > 8) return;
    const k = Math.round(h * 3) / 3;
    (bins.get(k) ?? bins.set(k, []).get(k)).push(c.folded.flux[i]);
  });
  const med = (a) => a.sort((x, y) => x - y)[a.length >> 1];
  out[c.id] = [...bins.entries()].sort((a, b) => a[0] - b[0]).map(([h, v]) => [Math.round(h * 100) / 100, Math.round(med(v) * 1e6) / 1e6]);
}
writeFileSync(new URL("../folds.mock.json", dir), JSON.stringify({ demo: true, note: "Binned folds of the simulated demo light curves", folds: out }));
console.log(Object.keys(out).length, "folds");

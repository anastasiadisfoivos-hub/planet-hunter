// Cuts ESO's all-sky panorama (eso0932a, "ESO/S. Brunier", CC BY 4.0) into what the site serves:
//   public/images/sky/eso0932a-6000.jpg  the 3D sky on desktop (6000 × 3000, ESO's largest JPEG)
//   public/images/sky/eso0932a-3072.jpg  the 3D sky on phones, and the fallback for crops (3072 × 1536)
//   public/images/sky/where/<event>.jpg  a 56° × 34° "where is it" crop around every event with a sky position
// and records each file in public/images/credits.json.
//
//   curl -L -o /tmp/eso0932a.jpg https://cdn.eso.org/images/large/eso0932a.jpg
//   node scripts/build-sky.mjs /tmp/eso0932a.jpg
//
// Uses sharp, which Next.js already installs for image optimisation.

import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import sharp from "sharp";
import { windowAround } from "../lib/galactic.ts";
import { pictureKey, WHERE_SPAN } from "../lib/pictureKeys.ts";

const src = process.argv[2];
if (!src) {
  console.error("usage: node scripts/build-sky.mjs <eso0932a large jpg>");
  process.exit(1);
}

const root = new URL("../public/", import.meta.url);
const creditsPath = new URL("images/credits.json", root);
const credits = JSON.parse(readFileSync(creditsPath, "utf8"));
const base = {
  url: "https://www.eso.org/public/images/eso0932a/",
  title: "The Milky Way panorama",
  credit: "ESO/S. Brunier",
  licence: "CC BY 4.0",
  source: "ESO",
  file: "https://cdn.eso.org/images/large/eso0932a.jpg",
};

const pano = sharp(src, { limitInputPixels: false });
const { width: W, height: H } = await pano.metadata();
mkdirSync(new URL("images/sky/where/", root), { recursive: true });

for (const w of [6000, 3072]) {
  const rel = `sky/eso0932a-${w}.jpg`;
  await sharp(src, { limitInputPixels: false }).resize(w, w / 2).jpeg({ quality: w > 4000 ? 78 : 80, progressive: true, mozjpeg: true }).toFile(new URL(`images/${rel}`, root).pathname);
  credits[rel] = { ...base, width: w, height: w / 2, note: "Equirectangular in galactic coordinates; lib/galactic.ts places everything on it" };
}
delete credits["sky/eso0932a.jpg"];

// Every event with a position on the sky gets a crop, so the compact sky never needs the full panorama.
const { events } = JSON.parse(readFileSync(new URL("data/events.mock.json", root), "utf8"));
const raw = await sharp(src, { limitInputPixels: false }).raw().toBuffer({ resolveWithObject: true });
let n = 0;
for (const e of events) {
  const loc = e.location;
  if (!loc || loc.frame !== "sky") continue;
  const win = windowAround(loc.ra_deg, loc.dec_deg, WHERE_SPAN.l, WHERE_SPAN.b, W, H);
  const w = Math.round(win.w);
  const h = Math.round(win.h);
  const x0 = Math.round(win.x0);
  const y0 = Math.round(win.y0);
  // Copy the window pixel by pixel, wrapping horizontally at l = 180.
  const ch = raw.info.channels;
  const out = Buffer.alloc(w * h * ch);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const sx = (((x0 + x) % W) + W) % W;
      raw.data.copy(out, (y * w + x) * ch, ((y0 + y) * W + sx) * ch, ((y0 + y) * W + sx + 1) * ch);
    }
  }
  const rel = `sky/where/${pictureKey(e.id)}.jpg`;
  await sharp(out, { raw: { width: w, height: h, channels: ch } }).jpeg({ quality: 78, progressive: true, mozjpeg: true }).toFile(new URL(`images/${rel}`, root).pathname);
  credits[rel] = { ...base, title: `The Milky Way panorama around ${e.title}`, width: w, height: h, event: e.id, note: "Crop of eso0932a" };
  n++;
}

writeFileSync(creditsPath, JSON.stringify(credits, null, 1) + "\n");
console.log(`panorama ${W}×${H} → 6000 and 3072 wide; ${n} where-crops; ${Object.keys(credits).length} credited pictures`);

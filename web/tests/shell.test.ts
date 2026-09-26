import { test } from "node:test";
import assert from "node:assert/strict";
import { currentSection, HOME, NAV } from "../components/shell/nav.ts";
import { dayGroup, eventHref, longUtc, shortName } from "../components/gallery/text.ts";
import nextConfig from "../next.config.ts";
import type { SkyEvent } from "../lib/contract.ts";

test("top bar: the wordmark goes home and the sections are Monitor, Candidates, Log, Methods", () => {
  assert.equal(HOME.href, "/");
  assert.deepEqual(
    NAV.map((n) => [n.label, n.href]),
    [
      ["Monitor", "/"],
      ["Candidates", "/candidates"],
      ["Log", "/log"],
      ["Methods", "/methods"],
    ],
  );
  assert.ok(!NAV.some((n) => ["/events", "/sky", "/lab"].includes(n.href)), "the retired sections are gone from the nav");
});

test("top bar: the current section covers its sub-pages", () => {
  assert.equal(currentSection("/"), "/");
  assert.equal(currentSection("/candidates"), "/candidates");
  assert.equal(currentSection("/candidates/tic415739607-01"), "/candidates");
  assert.equal(currentSection("/log"), "/log");
  assert.equal(currentSection("/sensitivity"), "/methods");
  assert.equal(currentSection("/methods"), "/methods");
  assert.equal(currentSection("/credits"), null);
  assert.equal(currentSection("/logbook"), null, "a prefix of a word is not a section");
});

test("/map redirects to /sky permanently (Next keeps the query, so shared filter links still work)", async () => {
  const redirects = await nextConfig.redirects!();
  assert.deepEqual(
    redirects.find((r) => r.source === "/map"),
    { source: "/map", destination: "/sky", permanent: true },
  );
});

const ev = (title: string, type: SkyEvent["type"] = "supernova") => ({ title, type }) as SkyEvent;

test("tile names drop what the glyph already says", () => {
  assert.equal(shortName(ev("Supernova candidate ZTF26abeqbvy")), "ZTF26abeqbvy");
  assert.equal(shortName(ev("Coronal mass ejection (805 km/s)", "coronal_mass_ejection")), "CME 805 km/s");
  assert.equal(shortName(ev("ZTF26abxaktw (known asteroid)", "asteroid")), "ZTF26abxaktw");
  assert.equal(shortName(ev("SN 2026abvs (SN IIn)")), "SN 2026abvs (SN IIn)");
});

test("gallery days are UTC: Today, Yesterday, then dates", () => {
  const now = Date.parse("2026-09-25T16:03:00Z");
  assert.equal(dayGroup("2026-09-25T00:10:00Z", now), "Today");
  assert.equal(dayGroup("2026-09-24T23:59:00Z", now), "Yesterday");
  assert.equal(dayGroup("2026-09-21T09:09:00Z", now), "21 Sep");
  assert.equal(longUtc("2026-09-25T11:49:00Z"), "25 Sep 2026, 11:49 UTC");
  assert.equal(eventHref("tns:2026abvs"), "/events/tns%3A2026abvs");
});

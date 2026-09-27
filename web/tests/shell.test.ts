import { test } from "node:test";
import assert from "node:assert/strict";
import { currentSection, HOME, NAV } from "../components/shell/nav.ts";

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

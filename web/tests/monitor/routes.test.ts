import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { finderTarget } from "../../components/finder/routes.ts";

test("/finder URLs move to the new pages", () => {
  assert.equal(finderTarget("/finder"), "/candidates");
  assert.equal(finderTarget("/finder/"), "/candidates");
  assert.equal(finderTarget("/finder/tic415739607-01"), "/candidates/tic415739607-01");
  assert.equal(finderTarget("/finder/sensitivity"), "/sensitivity");
  assert.equal(finderTarget("/finder/a/b"), "/candidates");
  assert.equal(finderTarget("/finder/%3Cscript%3E"), "/candidates", "anything that isn't an id goes to the list");
});

test("the /finder route handler redirects permanently (308) and keeps the query", async () => {
  const src = readFileSync(new URL("../../app/finder/[[...path]]/route.ts", import.meta.url), "utf8");
  assert.match(src, /finderTarget\(url\.pathname\)/);
  assert.match(src, /Response\.redirect\(to, 308\)/);
  assert.match(src, /to\.search = url\.search/);
  assert.match(src, /export const GET = move/);
});

// Against a running server: MONITOR_BASE=http://localhost:3000 node --test tests/monitor/redirects.http.test.ts
import { test } from "node:test";
import assert from "node:assert/strict";

const base = process.env.MONITOR_BASE;

test("the old /finder URLs answer 308 with the new place (live server)", { skip: !base && "set MONITOR_BASE to run" }, async () => {
  const cases: [string, string][] = [
    ["/finder", "/candidates"],
    ["/finder/tic415739607-01", "/candidates/tic415739607-01"],
    ["/finder/sensitivity", "/sensitivity"],
    ["/finder/tic75208638-01?from=mail", "/candidates/tic75208638-01?from=mail"],
  ];
  for (const [from, to] of cases) {
    const res = await fetch(base + from, { redirect: "manual" });
    assert.equal(res.status, 308, from);
    const loc = new URL(res.headers.get("location")!, base);
    assert.equal(loc.pathname + loc.search, to, from);
  }
});

import { test } from "node:test";
import assert from "node:assert/strict";
import { EXPLAIN } from "../../components/shell/explain.ts";

test("every screen has an explainer strip: 3 or 4 icons, two-word labels, one sentence each", () => {
  assert.deepEqual(Object.keys(EXPLAIN).sort(), ["candidates", "dossier", "log", "methods", "monitor", "sensitivity"]);
  for (const [screen, items] of Object.entries(EXPLAIN)) {
    assert.ok(items.length >= 3 && items.length <= 4, `${screen}: ${items.length} items`);
    for (const it of items) {
      assert.ok(it.label.split(/\s+/).length <= 2, `${screen}: "${it.label}" is more than two words`);
      assert.match(it.tip, /^[A-Z].*[.]$/, `${screen}: "${it.label}" tip is a sentence`);
      assert.ok(!/[.!?]\s+[A-Z]/.test(it.tip), `${screen}: "${it.label}" tip is one sentence`);
      assert.ok(!/\bdiscovered\b|new planet/i.test(it.tip), "never claims a discovery");
    }
    assert.equal(new Set(items.map((i) => i.icon)).size, items.length, `${screen}: one icon per item`);
  }
});

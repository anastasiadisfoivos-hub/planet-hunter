import { test } from "node:test";
import assert from "node:assert/strict";
import { listenDismiss } from "../../components/map/dismiss.ts";

/** A stand-in element: it knows its children and records focus. */
class El {
  focused = 0;
  kids: El[] = [];
  focus() {
    this.focused++;
  }
  contains(n: unknown): boolean {
    return n === this || this.kids.some((k) => k.contains(n));
  }
}

function key(root: EventTarget, k: string) {
  const e = new Event("keydown", { cancelable: true, bubbles: true });
  Object.defineProperty(e, "key", { value: k });
  root.dispatchEvent(e);
  return e;
}

function at(root: EventTarget, type: string, target: unknown) {
  const e = new Event(type);
  Object.defineProperty(e, "target", { value: target });
  root.dispatchEvent(e);
}

function setup() {
  const root = new EventTarget();
  const trigger = new El();
  const panel = new El();
  const inside = new El();
  panel.kids.push(inside);
  let closed = 0;
  const stop = listenDismiss({ root, trigger: trigger as never, panel: panel as never, onClose: () => closed++ });
  return { root, trigger, panel, inside, stop, closed: () => closed };
}

test("Esc closes the popover and returns focus to the button that opened it", () => {
  const t = setup();
  const e = key(t.root, "Escape");
  assert.equal(t.closed(), 1);
  assert.equal(t.trigger.focused, 1);
  assert.equal(e.defaultPrevented, true, "the map's own Esc (clear the selection) sees it handled");
});

test("other keys do nothing", () => {
  const t = setup();
  key(t.root, "Enter");
  key(t.root, "Tab");
  assert.equal(t.closed(), 0);
  assert.equal(t.trigger.focused, 0);
});

test("a press outside closes without moving focus; inside or on the button does not close", () => {
  const t = setup();
  at(t.root, "pointerdown", t.inside);
  at(t.root, "pointerdown", t.trigger);
  assert.equal(t.closed(), 0);
  at(t.root, "pointerdown", new El());
  assert.equal(t.closed(), 1);
  assert.equal(t.trigger.focused, 0);
});

test("focus leaving (Tab out) closes; focus moving inside does not", () => {
  const t = setup();
  at(t.root, "focusin", t.inside);
  assert.equal(t.closed(), 0);
  at(t.root, "focusin", new El());
  assert.equal(t.closed(), 1);
});

test("after stop, nothing is heard", () => {
  const t = setup();
  t.stop();
  key(t.root, "Escape");
  at(t.root, "pointerdown", new El());
  assert.equal(t.closed(), 0);
});

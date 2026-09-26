// Closing a popover or sheet the same way everywhere: Esc closes it and puts focus back on the button
// that opened it; a press outside both, or focus moving elsewhere (Tab), closes it without moving focus. Framework-free so it can be
// tested with plain EventTargets.

type Focusable = { focus: (opts?: FocusOptions) => void; contains: (n: Node | null) => boolean };

export type DismissOptions = {
  /** Where keydown and pointerdown are heard (the document). */
  root: EventTarget;
  trigger: Focusable;
  panel: Focusable;
  onClose: () => void;
};

const CAPTURE = { capture: true } as const;

/** Start listening. Returns a function that stops. */
export function listenDismiss({ root, trigger, panel, onClose }: DismissOptions): () => void {
  const onKey = (e: Event) => {
    if ((e as KeyboardEvent).key !== "Escape") return;
    // Handled here, so the map's own Esc (clear the selection) leaves the selection alone.
    e.preventDefault();
    e.stopPropagation();
    onClose();
    trigger.focus({ preventScroll: true });
  };
  const onOutside = (e: Event) => {
    const t = e.target as Node | null;
    if (panel.contains(t) || trigger.contains(t)) return;
    onClose();
  };
  // Capture phase, so this runs before the map's window-level Esc handler.
  root.addEventListener("keydown", onKey, CAPTURE);
  root.addEventListener("pointerdown", onOutside, CAPTURE);
  root.addEventListener("focusin", onOutside, CAPTURE);
  return () => {
    root.removeEventListener("keydown", onKey, CAPTURE);
    root.removeEventListener("pointerdown", onOutside, CAPTURE);
    root.removeEventListener("focusin", onOutside, CAPTURE);
  };
}

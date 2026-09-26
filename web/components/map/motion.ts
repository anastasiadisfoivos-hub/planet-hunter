// The little motion JavaScript the map needs where CSS cannot do it: FLIP for the feed and pausing
// running animations while the tab is hidden. Everything else is CSS transitions.

/** DESIGN.md curve and the UI duration for a list reorder. */
export const EASE = "cubic-bezier(0.2, 0, 0, 1)";
export const FLIP_MS = 200;

export function reducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/**
 * FLIP: given each item's previous top and its element now, slide it from where it was to where it is.
 * Returns the new tops for next time. Items that are new, unmoved, or moved more than a screen are left
 * alone (new ones have their own entrance).
 */
export function flip(prev: Map<string, number>, items: Iterable<{ id: string; el: HTMLElement }>, animate: boolean): Map<string, number> {
  const next = new Map<string, number>();
  for (const { id, el } of items) {
    const top = el.offsetTop;
    next.set(id, top);
    const was = prev.get(id);
    if (!animate || was === undefined || was === top || Math.abs(was - top) > window.innerHeight) continue;
    el.animate([{ transform: `translateY(${was - top}px)` }, { transform: "none" }], { duration: FLIP_MS, easing: EASE });
  }
  return next;
}

/** Pause every running animation and transition in the page while it is hidden; resume on return. */
export function pauseWhileHidden(): () => void {
  let paused: Animation[] = [];
  const onChange = () => {
    if (document.hidden) {
      paused = document.getAnimations().filter((a) => a.playState === "running");
      for (const a of paused) a.pause();
    } else {
      for (const a of paused) if (a.playState === "paused") a.play();
      paused = [];
    }
  };
  document.addEventListener("visibilitychange", onChange);
  return () => document.removeEventListener("visibilitychange", onChange);
}

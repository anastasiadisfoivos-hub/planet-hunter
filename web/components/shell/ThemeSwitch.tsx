"use client";

import { useSyncExternalStore } from "react";
import { Icon } from "@/components/monitor/Glyphs";
import s from "./shell.module.css";

// Day is the default; Night is a choice this browser remembers (DESIGN.md v3: Colour).
const KEY = "ph-theme";
const EVENT = "ph-theme";

function read(): "day" | "night" {
  return document.documentElement.dataset.theme === "night" ? "night" : "day";
}

function subscribe(cb: () => void) {
  window.addEventListener(EVENT, cb);
  return () => window.removeEventListener(EVENT, cb);
}

export function setTheme(t: "day" | "night") {
  if (t === "night") document.documentElement.dataset.theme = "night";
  else delete document.documentElement.dataset.theme;
  try {
    if (t === "night") localStorage.setItem(KEY, "night");
    else localStorage.removeItem(KEY);
  } catch {
    /* private mode: the choice lasts until reload */
  }
  window.dispatchEvent(new Event(EVENT));
}

/** Subscribe to theme changes (for canvases that read their inks from the tokens). */
export const onThemeChange = subscribe;

export function ThemeSwitch() {
  const theme = useSyncExternalStore(subscribe, read, () => "day" as const);
  const night = theme === "night";
  return (
    <button type="button" className={s.theme} aria-pressed={night} aria-label="Night theme" onClick={() => setTheme(night ? "day" : "night")} title={night ? "Night: tap for day" : "Day: tap for night"}>
      <Icon name={night ? "night" : "day"} size={20} />
      <span className={s.themeWord} aria-hidden>
        {night ? "Night" : "Day"}
      </span>
    </button>
  );
}

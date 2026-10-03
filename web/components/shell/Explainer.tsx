"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Icon, type IconName } from "@/components/monitor/Glyphs";
import s from "./explainer.module.css";

export type ExplainItem = { icon: IconName; label: string; tip: string };

/**
 * "What you're looking at" (DESIGN.md v3: The explainer strip): 3 or 4 icons with two-word labels. Each is a
 * toggletip: tap or press it for one sentence under it; Escape, a second tap or a tap elsewhere closes it.
 */
export function Explainer({ items, label = "What you're looking at" }: { items: ExplainItem[]; label?: string }) {
  const [open, setOpen] = useState<number | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const id = useId();
  useEffect(() => {
    if (open == null) return;
    const away = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(null);
    };
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(null);
    };
    document.addEventListener("pointerdown", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);
  return (
    <div className={s.strip} ref={root} role="group" aria-label={label}>
      {items.map((it, i) => (
        <div key={it.label} className={s.item}>
          <button type="button" className={s.btn} aria-expanded={open === i} aria-controls={`${id}-${i}`} onClick={() => setOpen((o) => (o === i ? null : i))}>
            <Icon name={it.icon} size={26} />
            <span className={s.word}>{it.label}</span>
          </button>
          <p id={`${id}-${i}`} className={s.tip} hidden={open !== i} role="note">
            {it.tip}
          </p>
        </div>
      ))}
    </div>
  );
}

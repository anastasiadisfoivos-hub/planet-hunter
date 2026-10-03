"use client";

import { useRef, type KeyboardEvent } from "react";
import s from "./ui.module.css";

export type SegmentedOption<T extends string> = { value: T; label: string };

export type SegmentedProps<T extends string> = {
  options: SegmentedOption<T>[];
  value: T;
  onChange: (value: T) => void;
  /** Accessible name for the group. */
  label: string;
  /** Stretch to the container width with equal segments. */
  block?: boolean;
  className?: string;
};

/** A radio group drawn as a segmented control. Arrow keys move the selection. */
export function Segmented<T extends string>({ options, value, onChange, label, block, className }: SegmentedProps<T>) {
  const ref = useRef<HTMLDivElement>(null);

  const onKey = (e: KeyboardEvent) => {
    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
    e.preventDefault();
    const i = options.findIndex((o) => o.value === value);
    const step = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
    const next = options[(i + step + options.length) % options.length];
    onChange(next.value);
    ref.current?.querySelector<HTMLButtonElement>(`[data-value="${next.value}"]`)?.focus();
  };

  return (
    <div
      ref={ref}
      role="radiogroup"
      aria-label={label}
      className={[s.segmented, block && s.segmentedBlock, className].filter(Boolean).join(" ")}
      onKeyDown={onKey}
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          data-value={o.value}
          aria-checked={o.value === value}
          tabIndex={o.value === value ? 0 : -1}
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

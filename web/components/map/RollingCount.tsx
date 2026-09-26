"use client";

import { useState } from "react";
import s from "./map.module.css";

/**
 * A number that rolls to its new value: the old digits slide out one way while the new ones slide in,
 * up when it grows, down when it shrinks. Pure CSS transitions via @starting-style; instant under
 * reduced motion. Screen readers get the plain value.
 */
export function RollingCount({ value, className }: { value: number; className?: string }) {
  const [shown, setShown] = useState(value);
  const [from, setFrom] = useState<{ value: number; to: number } | null>(null);
  if (shown !== value) {
    setFrom({ value: shown, to: value });
    setShown(value);
  }
  const dir = from && from.to === value ? (value > from.value ? "up" : "down") : undefined;
  return (
    <span className={[s.roll, className].filter(Boolean).join(" ")} data-dir={dir}>
      <span key={`in:${value}`} className={s.rollIn}>
        {value}
      </span>
      {from && from.to === value && (
        <span key={`out:${from.value}>${value}`} className={s.rollOut} aria-hidden>
          {from.value}
        </span>
      )}
    </span>
  );
}

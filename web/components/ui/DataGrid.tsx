import type { CSSProperties, ReactNode } from "react";
import s from "./ui.module.css";

export type DataGridItem = {
  label: string;
  value: ReactNode;
  /** Render the value in Geist Mono (numbers, coordinates, IDs). */
  mono?: boolean;
  /** Small secondary line under the value. */
  hint?: ReactNode;
  /** Span every column. */
  wide?: boolean;
};

/** Label/value cells in a hairline grid. Semantically a <dl>. */
export function DataGrid({ items, columns = 2, className }: { items: DataGridItem[]; columns?: number; className?: string }) {
  return (
    <dl className={[s.grid, className].filter(Boolean).join(" ")} style={{ "--cols": columns } as CSSProperties}>
      {items.map((it) => (
        <div key={it.label} className={[s.cell, it.mono && s.cellMono, it.wide && s.cellWide].filter(Boolean).join(" ")}>
          <dt>{it.label}</dt>
          <dd>{it.value}</dd>
          {it.hint && <span className={s.cellHint}>{it.hint}</span>}
        </div>
      ))}
    </dl>
  );
}

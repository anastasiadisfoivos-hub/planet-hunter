import type { ReactNode } from "react";
import s from "./picture.module.css";

/** A closed-by-default explanation (DESIGN.md, Drawers): a summary of ≤ 3 words and a mono state. */
export function Drawer({ title, state, children, id, open }: { title: string; state?: string; children: ReactNode; id?: string; open?: boolean }) {
  return (
    <details className={s.drawer} id={id} open={open}>
      <summary className={s.summary}>
        <span>{title}</span>
        {state && <span className={`cap ${s.state}`}>{state}</span>}
        <span className={s.marker} aria-hidden />
      </summary>
      <div className={s.body}>{children}</div>
    </details>
  );
}

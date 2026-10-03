import type { ReactNode } from "react";
import s from "./ui.module.css";

/** What a view shows before it has content: say what goes here and how to add it. */
export function EmptyState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className={s.empty}>
      <p className={s.emptyTitle}>{title}</p>
      {children && <div className={s.emptyBody}>{children}</div>}
      {action && <div className={s.emptyAction}>{action}</div>}
    </div>
  );
}

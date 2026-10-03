import type { HTMLAttributes, ReactNode } from "react";
import s from "./ui.module.css";

export type PanelProps = Omit<HTMLAttributes<HTMLElement>, "title"> & {
  title?: ReactNode;
  /** Right side of the header: small buttons, a count, a tag. */
  actions?: ReactNode;
  footer?: ReactNode;
  /** Remove body padding, for lists that run edge to edge. */
  flush?: boolean;
  as?: "section" | "aside" | "div";
};

/** A raised surface with an optional hairline header and footer. The body scrolls. */
export function Panel({ title, actions, footer, flush, as: Tag = "section", className, children, ...rest }: PanelProps) {
  return (
    <Tag className={[s.panel, flush && s.flush, className].filter(Boolean).join(" ")} {...rest}>
      {(title || actions) && (
        <header className={s.panelHead}>
          {typeof title === "string" ? <h2 className={s.panelTitle}>{title}</h2> : title}
          {actions && <div className={s.panelActions}>{actions}</div>}
        </header>
      )}
      <div className={s.panelBody}>{children}</div>
      {footer && <footer className={s.panelFooter}>{footer}</footer>}
    </Tag>
  );
}

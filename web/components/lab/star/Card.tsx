import type { ReactNode } from "react";
import { LockSimple } from "@phosphor-icons/react";
import { DemoTag, Tag } from "@/components/ui";
import s from "./star.module.css";
import l from "../lab.module.css";

export type DataKind = "real" | "demo" | "estimate" | "mixed";

/** One experiment on this star: working, or locked with the reason and what would unlock it. */
export function Card({ id, title, lede, locked, data, children }: {
  id: string;
  title: string;
  /** One line under the title: what the experiment does. */
  lede: ReactNode;
  /** When set, the card is locked: this is the reason, and `children` is the unlock action. */
  locked?: ReactNode;
  data?: DataKind;
  children?: ReactNode;
}) {
  return (
    <section className={s.card} id={id} data-locked={locked ? "true" : undefined} aria-labelledby={`${id}-h`}>
      <div className={s.cardHead}>
        <div className={s.cardTitle}>
          <h2 id={`${id}-h`} className={l.h2}>
            {title}
          </h2>
          <p className={l.body}>{lede}</p>
        </div>
        <div className={s.cardTags}>
          {locked ? <Tag>Locked</Tag> : data === "demo" ? <DemoTag /> : data === "real" ? <Tag>Real data</Tag> : data === "estimate" ? <Tag>Estimate</Tag> : null}
        </div>
      </div>
      {locked ? (
        <div className={s.lockBody}>
          <p className={s.lockLine}>
            <LockSimple size={14} aria-hidden />
            <span>{locked}</span>
          </p>
          {children}
        </div>
      ) : (
        children
      )}
    </section>
  );
}

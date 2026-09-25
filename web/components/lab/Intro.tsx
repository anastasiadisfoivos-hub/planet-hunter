import type { ReactNode } from "react";
import { DemoTag, Tag } from "@/components/ui";
import s from "./lab.module.css";

/** Page title, one-line lede and whether the data is real. */
export function Intro({ title, children, data }: { title: string; children: ReactNode; data: "real" | "demo" | "mixed" }) {
  return (
    <div className={s.intro}>
      <div className={s.titleRow}>
        <h1 className={s.h1}>{title}</h1>
        {data === "demo" ? <DemoTag /> : data === "real" ? <Tag>Real data</Tag> : null}
      </div>
      <p className={s.lede}>{children}</p>
    </div>
  );
}

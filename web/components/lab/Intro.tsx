import type { ReactNode } from "react";
import { DemoTag } from "@/components/ui";
import s from "./lab.module.css";

/** Page title, one-line lede, and a DEMO DATA tag when the page runs on stand-in data (real is the default; no tag). */
export function Intro({ title, children, data }: { title: string; children: ReactNode; data: "real" | "demo" | "mixed" }) {
  return (
    <div className={s.intro}>
      <div className={s.titleRow}>
        <h1 className={s.h1}>{title}</h1>
        {data === "demo" && <DemoTag />}
      </div>
      <p className={s.lede}>{children}</p>
    </div>
  );
}

"use client";

// The lab's frame: the index (/lab) draws its own full-bleed hero; experiment pages get the experiments as tabs
// under the top bar (DESIGN.md, Page header: section tabs), star labs a crumb back to the lab.

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowLeft } from "@phosphor-icons/react";
import { EXPERIMENTS } from "./LabNav";
import s from "./frame.module.css";

export function LabFrame({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  if (path === "/lab") return <>{children}</>;
  const inExperiment = EXPERIMENTS.some((e) => e.href === path);
  return (
    <main className={`wrap ${s.main}`}>
      {inExperiment ? (
        <nav className={s.tabs} aria-label="Experiments">
          {EXPERIMENTS.map((e) => (
            <Link key={e.href} href={e.href} className={s.tab} aria-current={path === e.href ? "page" : undefined}>
              {e.label}
            </Link>
          ))}
        </nav>
      ) : (
        <Link href="/lab" className={s.crumb}>
          <ArrowLeft size={14} aria-hidden /> Lab
        </Link>
      )}
      {children}
    </main>
  );
}

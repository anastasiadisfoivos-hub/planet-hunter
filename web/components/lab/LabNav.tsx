"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight } from "@phosphor-icons/react";
import s from "./lab.module.css";

export const EXPERIMENTS = [
  { href: "/lab/thermometer", label: "Star thermometer" },
  { href: "/lab/hear-a-star", label: "Hear a star" },
  { href: "/lab/hubble", label: "Hubble diagram" },
  { href: "/lab/fingerprints", label: "Chemical fingerprints" },
] as const;

export function LabHeader() {
  const path = usePathname();
  return (
    <header className={s.header}>
      <Link href="/lab" className={s.brand} aria-current={path === "/lab" ? "page" : undefined}>
        Planet Hunter <span>Lab</span>
      </Link>
      <nav className={s.nav} aria-label="Experiments">
        {EXPERIMENTS.map((e) => (
          <Link key={e.href} href={e.href} className={s.navLink} aria-current={path === e.href ? "page" : undefined}>
            {e.label}
          </Link>
        ))}
      </nav>
      <Link href="/map" className={s.mapLink}>
        Sky map
        <ArrowRight size={14} aria-hidden />
      </Link>
    </header>
  );
}

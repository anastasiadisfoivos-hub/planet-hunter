"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ArrowRight } from "@phosphor-icons/react";
import s from "@/components/lab/lab.module.css";

const LINKS = [
  { href: "/finder", label: "Candidates" },
  { href: "/finder/sensitivity", label: "What it can find" },
  { href: "/lab", label: "Lab" },
] as const;

export function FinderHeader() {
  const path = usePathname();
  const current = (href: string) => (href === "/finder" ? path === "/finder" || /^\/finder\/(?!sensitivity)/.test(path) : path.startsWith(href));
  return (
    <header className={s.header}>
      <Link href="/finder" className={s.brand}>
        Planet Hunter <span>Finder</span>
      </Link>
      <nav className={s.nav} aria-label="Finder">
        {LINKS.map((e) => (
          <Link key={e.href} href={e.href} className={s.navLink} aria-current={current(e.href) ? "page" : undefined}>
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

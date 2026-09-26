"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { MagnifyingGlass } from "@phosphor-icons/react";
import { StarSearch } from "./StarSearch";
import { currentSection, HOME, NAV } from "./nav";
import s from "./shell.module.css";

/**
 * The one top bar for every route (DESIGN.md, Components: Top bar). `over` lays it transparently over a hero
 * photograph (home, lab); `overAt` does so only on that exact path (a layout shared with pages that have no hero).
 * Otherwise it is sticky on black.
 */
export function TopBar({ over = false, overAt }: { over?: boolean; overAt?: string }) {
  const path = usePathname();
  const isOver = overAt ? path === overAt : over;
  const current = currentSection(path);
  return (
    <header className={s.bar} data-over={isOver || undefined}>
      <div className={`wrap ${s.inner}`}>
        <Link href={HOME.href} className={s.wordmark} aria-current={path === "/" ? "page" : undefined}>
          <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden>
            <circle cx="8" cy="8" r="7.25" fill="none" stroke="currentColor" strokeWidth="1.5" />
            <circle cx="8" cy="8" r="2.5" fill="currentColor" />
          </svg>
          <span className={s.wordmarkText}>{HOME.label}</span>
        </Link>
        <nav aria-label="Main" className={s.nav}>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={s.link} aria-current={current === n.href ? "page" : undefined}>
              {n.label}
            </Link>
          ))}
        </nav>
        <div className={s.end}>
          <button type="button" className={s.find} popoverTarget="find-star" aria-label="Find a star">
            <MagnifyingGlass size={15} aria-hidden />
            <span className={s.findText}>Find a star</span>
          </button>
          <div id="find-star" popover="auto" className={s.findPop}>
            <StarSearch />
          </div>
        </div>
      </div>
    </header>
  );
}

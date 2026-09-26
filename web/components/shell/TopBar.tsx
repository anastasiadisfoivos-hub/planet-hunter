"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { currentSection, HOME, NAV } from "./nav";
import s from "./shell.module.css";

/**
 * The top bar (DESIGN.md, Components: Top bar). `end` holds the monitor's mode label. It carries the `site` class
 * itself so it keeps its tokens on the retired pages that still render it.
 */
export function TopBar({ end }: { end?: React.ReactNode; over?: boolean; overAt?: string }) {
  const path = usePathname();
  const current = currentSection(path);
  return (
    <header className={`site ${s.bar}`}>
      <div className={`wrap ${s.inner}`}>
        <Link href={HOME.href} className={s.wordmark}>
          {HOME.label}
        </Link>
        <nav aria-label="Main" className={s.nav}>
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className={s.link} aria-current={current === n.href ? "page" : undefined}>
              {n.label}
            </Link>
          ))}
        </nav>
        {end ? <div className={s.end}>{end}</div> : null}
      </div>
    </header>
  );
}

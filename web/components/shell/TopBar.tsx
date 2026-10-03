"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Icon } from "@/components/monitor/Glyphs";
import { currentSection, HOME, NAV } from "./nav";
import { ThemeSwitch } from "./ThemeSwitch";
import s from "./shell.module.css";

/**
 * The top bar (DESIGN.md: Top bar): the name, then each section as an icon and one word, and the Day/Night switch.
 * It carries the `site` class itself so it keeps its tokens on the retired pages that still render it.
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
              <Icon name={n.icon} size={22} />
              <span>{n.label}</span>
            </Link>
          ))}
        </nav>
        <div className={s.end}>
          {end}
          <ThemeSwitch />
        </div>
      </div>
    </header>
  );
}

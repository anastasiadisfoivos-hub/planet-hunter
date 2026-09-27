// The top bar's links (DESIGN.md: Top bar). These are the only names for the sections, each with its icon.

export const HOME = { href: "/", label: "Planet Hunter" } as const;

export const NAV = [
  { href: "/", label: "Monitor", icon: "monitor" },
  { href: "/candidates", label: "Candidates", icon: "candidates" },
  { href: "/log", label: "Log", icon: "log" },
  { href: "/methods", label: "Methods", icon: "methods" },
] as const;

export type NavHref = (typeof NAV)[number]["href"];

/** Pages that belong to a section without being under its path. */
const BELONGS: Record<string, NavHref> = { "/sensitivity": "/methods" };

/** The section a path belongs to, for aria-current. /candidates/x is Candidates; / is only the Monitor. */
export function currentSection(path: string): NavHref | null {
  if (path === "/") return "/";
  for (const [p, href] of Object.entries(BELONGS)) if (path === p || path.startsWith(`${p}/`)) return href;
  const hit = NAV.find((n) => n.href !== "/" && (path === n.href || path.startsWith(`${n.href}/`)));
  return hit ? hit.href : null;
}

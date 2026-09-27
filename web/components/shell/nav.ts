// The top bar's links (DESIGN.md, Components: Top bar). These are the only names for the sections.

export const HOME = { href: "/", label: "Planet Hunter" } as const;

export const NAV = [
  { href: "/", label: "Monitor" },
  { href: "/candidates", label: "Candidates" },
  { href: "/log", label: "Log" },
  { href: "/methods", label: "Methods" },
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

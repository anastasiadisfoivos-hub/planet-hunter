// The one top bar's links (DESIGN.md, Components: Top bar). These are the only names for the sections.

export const HOME = { href: "/", label: "Planet Hunter" } as const;

export const NAV = [
  { href: "/events", label: "Events" },
  { href: "/sky", label: "Sky" },
  { href: "/lab", label: "Lab" },
  { href: "/finder", label: "Finder" },
] as const;

/** The section a path belongs to, for aria-current. /events/x is Events; /lab/star/1 is Lab. */
export function currentSection(path: string): (typeof NAV)[number]["href"] | null {
  const hit = NAV.find((n) => path === n.href || path.startsWith(`${n.href}/`));
  return hit ? hit.href : null;
}

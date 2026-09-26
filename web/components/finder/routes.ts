// Where the old /finder URLs go now (DESIGN.md: Other pages). No React and no "@/" value imports.

const ID = /^[a-z0-9-]{1,64}$/i;

/** /finder → /candidates, /finder/sensitivity → /sensitivity, /finder/<id> → /candidates/<id>. */
export function finderTarget(pathname: string): string {
  const rest = pathname.replace(/^\/finder\/?/, "").replace(/\/+$/, "");
  if (!rest) return "/candidates";
  if (rest === "sensitivity") return "/sensitivity";
  if (!rest.includes("/") && ID.test(rest)) return `/candidates/${rest}`;
  return "/candidates";
}

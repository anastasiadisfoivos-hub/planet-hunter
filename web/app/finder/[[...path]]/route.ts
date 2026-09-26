import { finderTarget } from "@/components/finder/routes";

/** The Finder became Candidates: every old /finder URL moves permanently, with its query kept. */
function move(request: Request): Response {
  const url = new URL(request.url);
  const to = new URL(finderTarget(url.pathname), url);
  to.search = url.search;
  return Response.redirect(to, 308);
}

export const GET = move;
export const HEAD = move;

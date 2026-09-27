"""Send a night's output to the API over HTTPS, then pixel-check what it asks for. The search
server runs this instead of `python -m api.finder_ingest`, so it needs no database URL: only the
API's address and PH_INGEST_TOKEN.

    PH_INGEST_TOKEN=... python -m api.remote_ingest --api-url https://... --dir RUN/candidates
        [--monitor-dir RUN/monitor] [--summary FILE] [--sensitivity FILE]
        --run-id ID [--run-started-at ISO] [--no-pixels] [--pixel-limit 20] [--time-budget-min 30]

1. POST /finder/ingest in chunks of at most --chunk-bytes: every <tic>_<n>.json (with its
   `vetting` block), every monitor/<tic>.json, the summary and the sensitivity; the last chunk
   has `final: true`, which marks the run done on the API.
2. GET /finder/pixel-queue, run pixels/ (`vet_pixels`, the `finder` extra) on each candidate
   here, and POST /finder/candidates/{id}/pixel-vet with the result or the error, until the
   queue is empty, --pixel-limit is reached or the time budget runs out.

Prints a JSON summary. Exits 1 when the API rejected an item or a request failed.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from api.finder import CANDIDATE_ID, normalize_vet
from api.finder_ingest import STAR_FILE, find_monitor, find_summary

log = logging.getLogger("api.remote_ingest")
TIMEOUT_S = 120.0


class Api:
    def __init__(self, base: str, token: str, retries: int = 3) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.retries = retries

    def call(self, method: str, path: str, body: Any = None) -> Any:
        data = None if body is None else json.dumps(body, allow_nan=False).encode()
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "planet-hunter-runner",
        }
        for attempt in range(self.retries + 1):
            req = urllib.request.Request(
                self.base + path, data=data, method=method, headers=headers
            )
            try:
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                    return json.loads(resp.read() or b"null")
            except urllib.error.HTTPError as exc:
                # 5xx (a free instance waking up, a deploy): retry; 4xx is our fault: stop.
                if exc.code < 500 or attempt == self.retries:
                    detail = exc.read()[:500].decode(errors="replace")
                    raise RuntimeError(f"{method} {path}: HTTP {exc.code} {detail}") from None
            except (urllib.error.URLError, OSError) as exc:
                if attempt == self.retries:
                    raise RuntimeError(f"{method} {path}: {exc}") from None
            time.sleep(min(60, 5 * 2**attempt))
        raise AssertionError("unreachable")


def _items(folder: Path | None, pattern) -> list[tuple[str, Any]]:
    if folder is None or not folder.is_dir():
        return []
    return [(p.stem, json.loads(p.read_text(encoding="utf-8")))
            for p in sorted(folder.glob("*.json")) if pattern.match(p.stem)]  # fmt: skip


def chunks(
    candidates: list[tuple[str, Any]], stars: list[Any], extra: dict[str, Any], max_bytes: int
) -> list[dict[str, Any]]:
    """Split into bodies of about `max_bytes` each. `extra` (summary, sensitivity) rides in the
    first; the last gets `final: true`. An item bigger than max_bytes still goes, alone."""
    out: list[dict[str, Any]] = []
    body: dict[str, Any] = {"candidates": [], "monitor": [], **extra}
    size = len(json.dumps(extra))
    items = [("candidates", {"id": cid, "candidate": c}) for cid, c in candidates]
    items += [("monitor", s) for s in stars]
    for key, item in items:
        n = len(json.dumps(item)) + 2
        if size + n > max_bytes and (body["candidates"] or body["monitor"]):
            out.append(body)
            body, size = {"candidates": [], "monitor": []}, 0
        body[key].append(item)
        size += n
    out.append(body)
    out[-1]["final"] = True
    return out


def send(api: Api, bodies: list[dict[str, Any]], run_id: str, started: str | None) -> dict:
    total: dict[str, Any] = {"chunks": 0, "created": 0, "updated": 0, "unchanged": 0,
                             "invalid": [], "dismissed": [], "monitor_stars": 0}  # fmt: skip
    for body in bodies:
        r = api.call(
            "POST", "/finder/ingest", {"run_id": run_id, "run_started_at": started, **body}
        )
        total["chunks"] += 1
        for k in ("created", "updated", "unchanged"):
            total[k] += r["candidates"][k]
        total["invalid"] += r["invalid"]
        total["dismissed"] += r["dismissed"]
        total["monitor_stars"] += r["monitor_stars"]
    return total


def pixel_checks(api: Api, vetter, limit: int, deadline: float, clock=time.monotonic) -> dict:
    out = {"vetted": 0, "failed": 0, "stale": 0, "skipped_for_time": 0}
    done: set[str] = set()
    while out["vetted"] + out["failed"] < limit:
        queue = [i for i in api.call("GET", f"/finder/pixel-queue?limit={min(limit, 100)}")["items"]
                 if i["id"] not in done]  # fmt: skip
        if not queue:
            break
        for item in queue:
            if clock() >= deadline or out["vetted"] + out["failed"] >= limit:
                out["skipped_for_time"] += int(clock() >= deadline)
                return out
            done.add(item["id"])
            body: dict[str, Any] = {"ephemeris_key": item["ephemeris_key"]}
            try:
                body["vet"] = normalize_vet(vetter.vet(item["candidate"]))
            except Exception as exc:  # noqa: BLE001 - any pixels/ failure is stored and retried
                body["error"] = f"{type(exc).__name__}: {exc}"[:500]
                log.warning("pixel check failed for %s: %s", item["id"], exc)
            try:
                api.call("POST", f"/finder/candidates/{item['id']}/pixel-vet", body)
            except RuntimeError as exc:
                if "HTTP 409" in str(exc):  # its ephemeris changed meanwhile: queued again
                    out["stale"] += 1
                    continue
                raise
            out["vetted" if "vet" in body else "failed"] += 1
    return out


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="python -m api.remote_ingest", description=__doc__.split("\n")[0]
    )
    p.add_argument("--api-url", default=os.environ.get("PH_API_URL"), help="default: PH_API_URL")
    p.add_argument("--dir", required=True, type=Path, help="the night's candidates folder")
    p.add_argument("--monitor-dir", type=Path, help="the run's monitor/ folder (default: found)")
    p.add_argument("--summary", type=Path, help="sweep summary JSON (default: found)")
    p.add_argument("--sensitivity", type=Path)
    p.add_argument("--run-id", required=True)
    p.add_argument("--run-started-at")
    p.add_argument("--chunk-bytes", type=int, default=4_000_000)
    p.add_argument("--pixel-limit", type=int, default=20)
    p.add_argument("--time-budget-min", type=float, default=30.0)
    p.add_argument("--no-pixels", action="store_true")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    token = os.environ.get("PH_INGEST_TOKEN")
    if not args.api_url or not token:
        p.error("needs --api-url (or PH_API_URL) and PH_INGEST_TOKEN")
    deadline = time.monotonic() + args.time_budget_min * 60
    api = Api(args.api_url, token)

    extra: dict[str, Any] = {}
    summary = args.summary or find_summary(args.dir)
    if summary is not None:
        extra["summary"] = json.loads(summary.read_text(encoding="utf-8"))
    if args.sensitivity is not None:
        extra["sensitivity"] = json.loads(args.sensitivity.read_text(encoding="utf-8"))
    monitor_dir = args.monitor_dir or (find_monitor(args.dir) if args.dir.exists() else None)
    candidates = _items(args.dir, CANDIDATE_ID)
    stars = [s for _, s in _items(monitor_dir, STAR_FILE)]

    result: dict[str, Any] = {"run_id": args.run_id, "pixels": None, "error": None}
    try:
        bodies = chunks(candidates, stars, extra, args.chunk_bytes)
        result["ingest"] = send(api, bodies, args.run_id, args.run_started_at)
        if not args.no_pixels:
            try:
                from api.settings import Settings
                from api.wiring import build_pixel_vetter

                vetter = build_pixel_vetter(Settings.from_env())
            except ImportError as exc:
                result["pixels"] = {"unavailable": f"pixels not installed: {exc}"}
            else:
                result["pixels"] = pixel_checks(api, vetter, args.pixel_limit, deadline)
    except RuntimeError as exc:
        result["error"] = str(exc)
    print(json.dumps(result, indent=1))
    return 1 if result["error"] or result.get("ingest", {}).get("invalid") else 0


if __name__ == "__main__":
    sys.exit(main())

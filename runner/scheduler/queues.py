"""Queue policy: which star each queue searches next, and which queue a free worker serves.

Three search queues. Each goes down its own ranked list, skipping what the ledger says is finished:

  fast   hunt/'s ranked list (targets.csv from `hunt targets`: known hosts B interleaved with new stars A,
         M dwarfs -> small stars -> other dwarfs, smaller then brighter first), in list order.
         The fast pass: the newest 3 sectors, BLS only (no TLS, no single/duo search). A star the deep pass
         already finished on the same sectors is skipped: the deep search covers everything the fast one does.
  deep   the deep pass (every sector stitched, BLS short + long, TLS, single/duo dips), in this order:
           1. stars the fast pass flagged as promising (a candidate, or a periodic signal at SNR >= 7 that
              failed only on SDE / number of transits / a check), best first;
           2. DEEPHUNT's group 0 of the ranked list: >= 5 sectors, Tmag <= 11, quiet dwarfs;
           3. group 1: every other star with >= 5 sectors.
  faint  faint/'s tier-1 M dwarfs (Tmag 13-16, TGLC light curves, >= 3 sectors), in rank order, deep search.

Split: each queue has a share of the night's worker-seconds (PH_SPLIT, default fast 45 %, deep 40 %, faint 15 %).
When a worker is free it serves the queue furthest below its share: time used so far plus the expected time
of its running stars, divided by its share. A queue with nothing left drops out and the others share its time.
Candidates are vetted (skyvet) on at most PH_VET_SLOTS workers (default 1) as soon as they appear.
"""

from __future__ import annotations

import csv
import gzip
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path

from scheduler.ledger import Ledger

PROMISING_MIN_SNR = 7.0
DEEP_GROUPS = ("0", "1")
FAINT_TIER = "1"
# Before the ledger has measured a queue: seconds per star on one core (DEEPHUNT and FAINT's measurements).
PRIOR_ELAPSED_S = {"fast": 60.0, "deep": 250.0, "faint": 90.0}


def read_rows(path: Path) -> list[dict]:
    """Rows of a targets CSV (plain or .gz), or of a file with one TIC per line."""
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", newline="") as fh:
        text = fh.read()
    lines = text.splitlines()
    first = next((ln for ln in lines if ln.strip()), "")
    if "tic" in [c.strip() for c in first.split(",")]:
        return [r for r in csv.DictReader(lines) if (r.get("tic") or "").strip()]
    return [{"tic": ln.split(",")[0].strip()} for ln in lines if ln.strip() and not ln.startswith("#")]


def sectors_key(row: dict) -> str:
    """The sectors a list says a star has. A new public sector changes the key, and the ledger lets that star be
    searched again. Rows without sector columns get "" (searched once)."""
    parts: set[int] = set()
    for col in ("sectors", "sectors_2min", "sectors_ffi"):
        for tok in (row.get(col) or "").replace(";", " ").replace(",", " ").split():
            if tok.isdigit():
                parts.add(int(tok))
    if parts:
        return " ".join(str(s) for s in sorted(parts))
    n = (row.get("n_sectors") or "").strip()
    return f"n={n}" if n else ""


@dataclass
class Queue:
    """One queue's ordered candidates for tonight. `rows` is consulted lazily, so the deep queue can see stars
    the fast pass promotes during the night."""
    name: str
    source: Callable[[], Iterator[dict]]
    ledger: Ledger
    limit: int | None = None  # stars per run (dry runs)
    skip_if_done_in: tuple[str, ...] = ()
    started: int = 0
    _it: Iterator[dict] | None = field(default=None, repr=False)
    _seen: set[int] = field(default_factory=set, repr=False)
    _exhausted: bool = False

    def reset(self) -> None:
        self._it, self._exhausted = None, False

    @property
    def exhausted(self) -> bool:
        return self._exhausted or (self.limit is not None and self.started >= self.limit)

    def next(self, run_id: str) -> dict | None:
        """Claim and return the next eligible row, or None when the queue has nothing left tonight."""
        if self.exhausted:
            return None
        blocked = self.ledger.blocked(self.name)
        others = [self.ledger.blocked(q) for q in self.skip_if_done_in]
        if self._it is None:
            self._it = self.source()
        for row in self._it:
            try:
                tic = int(str(row["tic"]).strip())
            except (KeyError, ValueError):
                continue
            if tic in self._seen:
                continue
            key = sectors_key(row)
            if tic in blocked and (blocked[tic] is None or blocked[tic] == key):
                continue
            if any(o.get(tic) == key and tic in o for o in others):
                continue
            if self.ledger.claim(self.name, tic, key, run_id):
                self._seen.add(tic)
                self.started += 1
                return {**row, "tic": tic, "sectors_key": key}
        self._exhausted = True
        return None


def _rows(path: Path | None) -> list[dict]:
    return read_rows(path) if path is not None and path.exists() else []


def build_queues(ledger: Ledger, targets_file: Path | None, faint_file: Path | None,
                 enabled: dict[str, bool], limit: int | None = None) -> dict[str, Queue]:
    bright = _rows(targets_file)
    by_tic = {}
    for r in bright:
        try:
            by_tic.setdefault(int(r["tic"]), r)
        except (KeyError, ValueError):
            pass

    def fast_rows() -> Iterator[dict]:
        yield from bright

    def deep_rows() -> Iterator[dict]:
        # 1. promoted by the fast pass (re-read each time the deep queue restarts its walk)
        for p in ledger.promising("fast"):
            base = by_tic.get(p["tic"], {"tic": p["tic"]})
            yield {**base, "tic": p["tic"], "promoted": True}
        # 2-3. DEEPHUNT's groups; a list without a group column (plain TIC list) is all taken as group 1
        has_group = bool(bright) and "group" in bright[0]
        for g in DEEP_GROUPS:
            for r in bright:
                if (r.get("group") if has_group else "1") == g:
                    yield r

    faint_all = _rows(faint_file)

    def faint_rows() -> Iterator[dict]:
        for r in faint_all:
            if (r.get("tier") or FAINT_TIER) == FAINT_TIER:
                yield {**r, "list": "A"}  # the faint list excludes known hosts: nothing to mask

    queues = {
        "fast": Queue("fast", fast_rows, ledger, limit, skip_if_done_in=("deep",)),
        "deep": Queue("deep", deep_rows, ledger, limit),
        "faint": Queue("faint", faint_rows, ledger, limit),
    }
    return {k: q for k, q in queues.items() if enabled.get(k, True)}


def expected_s(ledger: Ledger, queue: str) -> float:
    return ledger.mean_elapsed(queue) or PRIOR_ELAPSED_S[queue]


def pick_queue(queues: dict[str, Queue], split: dict[str, float], used_s: dict[str, float],
               running: dict[str, int], expected: dict[str, float]) -> str | None:
    """The queue furthest below its share of worker-seconds, counting running stars at their expected cost.
    Ties go to the order fast, deep, faint."""
    best, best_load = None, None
    for name in ("fast", "deep", "faint"):
        q = queues.get(name)
        share = split.get(name, 0.0)
        if q is None or share <= 0 or q.exhausted:
            continue
        load = (used_s.get(name, 0.0) + running.get(name, 0) * expected.get(name, 60.0)) / share
        if best_load is None or load < best_load - 1e-9:
            best, best_load = name, load
    return best


def plan(split: dict[str, float], workers: int, search_s: float, expected: dict[str, float],
         names: list[str]) -> dict[str, int]:
    """Stars each queue should finish tonight at its share (the `total` posted to the monitor)."""
    live = {n: split.get(n, 0.0) for n in names if split.get(n, 0.0) > 0}
    total = sum(live.values()) or 1.0
    return {n: int(workers * search_s * (s / total) / max(expected.get(n, 60.0), 1.0)) for n, s in live.items()}

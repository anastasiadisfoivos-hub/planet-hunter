"""Discovery ID rules from contracts/CONVENTIONS.md."""

from __future__ import annotations

import re

from api.contract import Discovery

RUBIN_ID = re.compile(r"^rubin:(obj|ss):[A-Za-z0-9_-]+$")
TESS_ID = re.compile(r"^tess:(\d+):(sig|flare):(.+)$")

PERIOD_TOLERANCE = 0.01
ALIAS_FACTORS = (1.0, 2.0, 3.0, 0.5, 1 / 3)


def flare_id(tic_id: int, peak_btjd: float) -> str:
    return f"tess:{tic_id}:flare:{round(peak_btjd, 2):.2f}"


def signal_id(tic_id: int, n: int) -> str:
    return f"tess:{tic_id}:sig:{n}"


def signal_number(discovery_id: str) -> int | None:
    m = TESS_ID.match(discovery_id)
    if not m or m.group(2) != "sig" or not m.group(3).isdigit():
        return None
    return int(m.group(3))


def period_match_error(p_new: float, p_old: float) -> float | None:
    """Relative error of the best alias match (1, 2, 3, 1/2, 1/3), or None if outside 1%."""
    if p_new <= 0 or p_old <= 0:
        return None
    ratio = p_new / p_old
    # Factors are ordered so a direct match wins over an alias when both qualify.
    for k in ALIAS_FACTORS:
        err = abs(ratio - k) / k
        if err <= PERIOD_TOLERANCE:
            return err
    return None


def _period(d: Discovery) -> float | None:
    p = d.raw.get("period_days")
    if isinstance(p, bool) or not isinstance(p, (int, float)):
        return None
    return float(p)


def normalize_rubin(discoveries: list[Discovery]) -> tuple[list[Discovery], list[str]]:
    """Keep only Rubin discoveries whose IDs follow the object-level convention."""
    kept, rejected = [], []
    for d in discoveries:
        if d.source == "rubin" and RUBIN_ID.match(d.id):
            kept.append(d)
        else:
            rejected.append(d.id)
    return kept, rejected


def assign_tess_ids(
    tic_id: int, found: list[Discovery], existing: list[Discovery]
) -> tuple[list[Discovery], list[str]]:
    """Give a hunt's results their final IDs.

    Flares are keyed by peak time. Transit signals are matched to the star's existing
    signals by period (within 1%, or a clean alias). A match reuses that ID; anything else
    gets the next free number. Two results matching the same existing signal are the same
    object, so only the closer one is kept.
    """
    out: list[Discovery] = []
    rejected: list[str] = []
    signals: list[tuple[Discovery, float]] = []

    for d in found:
        m = TESS_ID.match(d.id)
        if d.source != "tess" or not m or int(m.group(1)) != tic_id:
            rejected.append(d.id)
            continue
        if m.group(2) == "flare":
            peak = d.raw.get("peak_btjd")
            if isinstance(peak, bool) or not isinstance(peak, (int, float)):
                rejected.append(d.id)
                continue
            out.append(d.model_copy(update={"id": flare_id(tic_id, float(peak))}))
        else:
            period = _period(d)
            if period is None or period <= 0:
                rejected.append(d.id)
                continue
            signals.append((d, period))

    old = [(e, _period(e)) for e in existing if signal_number(e.id) is not None]
    old = [(e, p) for e, p in old if p is not None]

    candidates = []
    for i, (_d, p_new) in enumerate(signals):
        for e, p_old in old:
            err = period_match_error(p_new, p_old)
            if err is not None:
                candidates.append((err, i, e.id))
    candidates.sort()

    assigned: dict[int, str] = {}
    claimed: set[str] = set()
    for _err, i, eid in candidates:
        if i in assigned or eid in claimed:
            continue
        assigned[i] = eid
        claimed.add(eid)
    # Matched an existing signal that a closer result already took: same object, drop it.
    dropped = {i for _err, i, _eid in candidates if i not in assigned}

    next_n = max((signal_number(e.id) or 0 for e in existing), default=0) + 1
    for i, (d, _p) in enumerate(signals):
        if i in dropped:
            rejected.append(d.id)
            continue
        if i in assigned:
            new_id = assigned[i]
        else:
            new_id = signal_id(tic_id, next_n)
            next_n += 1
        out.append(d.model_copy(update={"id": new_id}))
    return out, rejected

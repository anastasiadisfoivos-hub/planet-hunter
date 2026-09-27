"""The monitor's star record (api/src/api/monitor.py, web/lib/api.ts MonitorStar), built from hunt's result:

  {tic, tmag, teff, radius_rsun, ra, dec, sectors, observed_from, observed_to, lightcurve: {t, f},
   detections: [{t0, duration_h, depth_ppm, period_d|null, kind, outcome, reason}], outcome, searched_at}

Detection outcomes follow the monitor's words: "candidate" (passed every stage), "known" (a listed planet,
candidate or binary on this star or a neighbour; also the listed planets masked before a sibling search),
"rejected" (failed a stage; `reason` says which, in words). The star's outcome is the strongest of its
detections (candidate > known > rejected), else "none".

The light curve is the searched curve normalised per sector and binned (10 min, wider for long baselines so it
stays under MAX_POINTS). Only the resolution is reduced; nothing is modelled.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime

import numpy as np

MAX_POINTS = 4000
BASE_BIN_MIN = 10


def iso_from_btjd(t: float) -> str:
    unix = (t + 2457000 - 2440587.5) * 86400
    return datetime.fromtimestamp(unix, UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def clean(x):
    """JSON-safe: NaN / inf -> None, numpy scalars -> Python."""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [clean(v) for v in x]
    if isinstance(x, np.generic):
        x = x.item()
    if isinstance(x, float) and not math.isfinite(x):
        return None
    return x


def binned_curve(time: np.ndarray, flux: np.ndarray, sector: np.ndarray) -> tuple[dict | None, int]:
    ok = np.isfinite(time) & np.isfinite(flux)
    time, flux, sector = time[ok], flux[ok], sector[ok]
    if len(time) < 10:
        return None, BASE_BIN_MIN
    days = 0.0
    for s in np.unique(sector):
        t = time[sector == s]
        days += len(np.unique(np.floor(t * 144)))  # 10-min slots with data
    minutes = BASE_BIN_MIN * max(1, math.ceil(days / MAX_POINTS))
    width = minutes / 1440
    ts, fs = [], []
    for s in np.unique(sector):
        m = sector == s
        t, f = time[m], flux[m]
        if len(t) < 3:
            continue
        med = np.nanmedian(f)
        if not np.isfinite(med) or med == 0:
            continue
        f = f / med
        k = np.floor((t - t[0]) / width).astype(np.int64)
        cnt = np.bincount(k)
        keep = cnt >= 1
        ts.append((np.bincount(k, weights=t) / np.maximum(cnt, 1))[keep])
        fs.append((np.bincount(k, weights=f) / np.maximum(cnt, 1))[keep])
    if not ts:
        return None, minutes
    t, f = np.concatenate(ts), np.concatenate(fs)
    order = np.argsort(t)
    return {"t": [round(float(x), 4) for x in t[order]], "f": [round(float(x), 5) for x in f[order]]}, minutes


def _kind_of(n_transits: int | None) -> str:
    n = n_transits or 0
    return "periodic" if n >= 3 else "duo" if n == 2 else "single"


def reason_for(rec: dict) -> str:
    stage = rec.get("failed_stage")
    if stage is None:
        return ("Passed every check and is on none of the lists of known planets, candidates and binaries we "
                "checked.")
    snr, sde, n = rec.get("snr"), rec.get("sde"), rec.get("n_transits")
    if stage == "snr":
        return f"Too faint: the dip stands {snr:.1f} times above the noise; the search needs more." if snr else \
            "Too faint to stand out from the noise."
    if stage == "sde":
        return f"Does not stand out from other periods in the search (SDE {sde:.1f}; the search needs 9)." \
            if sde is not None else "Does not stand out from other periods in the search."
    if stage == "transits":
        return f"Only {n} dips; the search needs at least 3 on one period."
    if stage in ("known", "neighbour"):
        names = ", ".join((rec.get("known_names") or [])[:2]) or "a listed object"
        where = "on this star" if stage == "known" else "on a neighbouring star"
        return f"Already known {where}: {names}."
    if stage == "neighbour_dips":
        return "Nearby stars dip at the same time: a spacecraft or sky artefact, not a transit."
    reasons = rec.get("failed_reasons") or {}
    if reasons:
        return str(next(iter(reasons.values())))
    failed = rec.get("failed_checks") or []
    return f"Failed the {', '.join(failed)} check{'s' if len(failed) > 1 else ''}." if failed else \
        "Failed the checks."


def _outcome(stage: str | None) -> str:
    return "candidate" if stage is None else "known" if stage in ("known", "neighbour") else "rejected"


def detections(summary: dict, listed_durations: dict[str, float] | None = None) -> list[dict]:
    listed_durations = listed_durations or {}
    out: list[dict] = []
    groups: list[list[dict]] = []
    for m in summary.get("masked_known") or []:
        if "(as found in the data)" in m.get("name", "") or not m.get("period_d"):
            continue
        g = next((g for g in groups if abs(g[0]["period_d"] / m["period_d"] - 1) < 0.01), None)
        (g.append(m) if g is not None else groups.append([m]))
    for g in groups:
        names = [m["name"] for m in g]
        m = g[0]
        dur = listed_durations.get(names[0]) or m.get("mask_half_width_h")
        also = f" (also listed as {', '.join(names[1:])})" if len(names) > 1 else ""
        out.append({"t0": m.get("t0_btjd"), "duration_h": round(float(dur), 3) if dur else None,
                    "depth_ppm": None, "period_d": m["period_d"], "kind": "periodic", "outcome": "known",
                    "reason": f"Already known: {names[0]}{also}. Its dips were masked before the search."})
    for rec in summary.get("signals") or []:
        kind = _kind_of(rec.get("n_transits"))
        out.append({"t0": rec.get("t0_btjd"), "duration_h": rec.get("duration_h"), "depth_ppm": rec.get("depth_ppm"),
                    "period_d": rec.get("period_d") if kind != "single" else None, "kind": kind,
                    "outcome": _outcome(rec.get("failed_stage")), "reason": reason_for(rec),
                    "id": str(rec.get("n")), "snr": rec.get("snr"), "sde": rec.get("sde"),
                    "n_transits": rec.get("n_transits"),
                    "failed_checks": rec.get("failed_checks") or []})
    for rec in summary.get("dips") or []:
        mids = rec.get("mid_times_btjd") or [None]
        out.append({"t0": mids[0], "duration_h": rec.get("duration_h"), "depth_ppm": rec.get("depth_ppm"),
                    "period_d": rec.get("period_d"), "kind": rec.get("kind") or "single",
                    "outcome": _outcome(rec.get("failed_stage")), "reason": reason_for(rec),
                    "id": f"{(rec.get('kind') or 'single')[0]}{rec.get('n')}", "snr": rec.get("snr"),
                    "mid_times_btjd": rec.get("mid_times_btjd"),
                    "period_range_d": rec.get("period_range_d"), "failed_checks": rec.get("failed_checks") or []})
    return out


def star_outcome(dets: list[dict]) -> str:
    kinds = {d["outcome"] for d in dets}
    for o in ("candidate", "known", "rejected"):
        if o in kinds:
            return o
    return "none"


def build(summary: dict, time: np.ndarray, flux: np.ndarray, sector: np.ndarray, *, queue: str,
          searched_at: str | None = None, listed_durations: dict[str, float] | None = None) -> dict:
    st = summary.get("star") or {}
    curve, minutes = binned_curve(np.asarray(time, float), np.asarray(flux, float), np.asarray(sector))
    ok = np.isfinite(time)
    dets = detections(summary, listed_durations)
    return clean({
        "tic": int(summary["tic"]),
        "tmag": st.get("tmag"), "teff": st.get("teff"), "radius_rsun": st.get("rad"),
        "ra": None if st.get("ra") is None else round(float(st["ra"]), 5),
        "dec": None if st.get("dec") is None else round(float(st["dec"]), 5),
        "sectors": [int(s) for s in summary.get("sectors") or []],
        "observed_from": iso_from_btjd(float(np.min(time[ok]))) if ok.any() else None,
        "observed_to": iso_from_btjd(float(np.max(time[ok]))) if ok.any() else None,
        "lightcurve": curve,
        "bin_minutes": minutes,
        "detections": dets,
        "outcome": star_outcome(dets),
        "search": queue,
        "searched_at": searched_at or datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
    })


def promising(summary: dict) -> bool:
    """Worth the deep pass: a candidate, or a periodic signal at SNR >= 7 that failed only on SDE, on the number
    of transits, or on a check (the deep search's extra sectors can fix all three)."""
    for rec in summary.get("signals") or []:
        stage = rec.get("failed_stage")
        if stage is None:
            return True
        if (rec.get("snr") or 0) >= 7.0 and stage in ("sde", "transits", "checks"):
            return True
    return any(r.get("failed_stage") is None for r in summary.get("dips") or [])

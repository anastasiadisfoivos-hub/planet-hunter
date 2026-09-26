"""One star: mask known transits -> periodic search -> checks -> known lists -> filter -> score -> candidates,
then the single / double dip search on what is left.

Periodic filter (a signal must pass every stage, in this order; the first stage it fails is recorded):
  snr       SNR >= 10
  sde       SDE >= 9
  transits  >= 3 transits with data
  checks    no check failed, and every must-run check actually ran (checks.MUST_RUN)
  known     period does not match (1% or x2, x3, 1/2, 1/3) a confirmed planet, TOI, CTOI or catalogued EB on
            this star
  neighbour ... nor on a listed star within 2.5 arcmin (likely the source of the dips)

Single / duo filter (singles.py): snr (SES >= 10; duo: combined >= 10 and each dip >= 7) -> checks (no check
failed, every must-run check ran: singles.SINGLE_MUST_RUN / DUO_MUST_RUN) -> known -> neighbour (listed
signal on this star or a neighbour predicts a transit at a dip time, or a duo alias matches a listed period).
At merge a further stage, neighbour_dips, drops dips seen at the same time in 2+ nearby stars.

Score (0-1, transparent), one formula for every kind:
  score = K_kind * (0.40 * S_snr + 0.20 * S_orbit + 0.25 * S_checks + 0.15 * S_bright)
  K_kind     periodic 1.0 (x 0.8 if all dips are in one sector), duo 0.5, single 0.3
  S_snr      = 1 - exp(-(SNR - 10) / 20)            0 at the SNR cut, 0.63 at SNR 30
  S_orbit    periodic: S_transits = 1 - exp(-(N - 3) / 6)   0 at 3 transits, 0.63 at 9
             duo: 1 / (number of surviving period aliases)   single: 0 (no period)
  S_checks   = mean check margin (0 at a check's threshold, 1 far inside it)
  S_bright   = clip((13 - Tmag) / 5, 0, 1)          0 at Tmag 13, 1 at Tmag 8 (follow-up is easier)
  So a single scores at most 0.3 x 0.8 = 0.24 and a duo at most 0.5; a periodic candidate can reach 1.
  score_parts = {snr, transits, checks, brightness} (transits = the S_orbit term): each term's contribution,
  weight * S * K, so the four parts add up to the score.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from hunter.search import Signal, bin_by_time, in_transit

from . import checks as chk
from . import singles as sg
from .catalogs import Catalogue
from .lightcurve import BIN_MINUTES, StarLC, bin_lc
from .signals import CONTINUE_MIN_SNR, MaskedPlanet, find_signals, known_transit_mask
from .stars import Star

MIN_SNR = 10.0
MIN_SDE = 9.0
MIN_TRANSITS = 3
STAGES = ("snr", "sde", "transits", "checks", "known", "neighbour")
DIP_STAGES = ("snr", "checks", "known", "neighbour", "neighbour_dips")
SINGLE_SECTOR_FACTOR = 0.8
KIND_FACTOR = {"periodic": 1.0, "duo": 0.5, "single": 0.3}
MAX_LEAK_ROUNDS = 3
W_SNR, W_TRANSITS, W_MARGIN, W_BRIGHT = 0.40, 0.20, 0.25, 0.15
UNFOLDED_MAX_POINTS = 6000
NOTE = ("A planet candidate from an automated search, not a confirmed planet. It needs review by people and "
        "follow-up observations; other things, such as a faint background binary, can look the same.")
DIP_NOTE = {"single": " Only one dip was seen, so the period is not known: it is estimated from how long the dip "
                      "lasts and the star's density, and could be anywhere in the range given.",
            "duo": " Only two dips were seen, so the period is one of the listed values (the gap between the dips "
                   "divided by a whole number) that the rest of the data allow."}


def _score(kind: str, snr: float, s_orbit: float, checks: list[chk.Check], tmag: float | None,
           single_sector: bool, min_snr: float) -> dict:
    s_snr = 1 - math.exp(-max(snr - min_snr, 0) / 20)
    margins = [c.margin for c in checks if c.margin is not None]
    s_margin = float(np.mean(margins)) if margins else 0.0
    s_bright = min(1.0, max(0.0, (13 - tmag) / 5)) if tmag is not None else 0.0
    factor = KIND_FACTOR[kind] * (SINGLE_SECTOR_FACTOR if single_sector else 1.0)
    parts = {"snr": W_SNR * s_snr * factor, "transits": W_TRANSITS * s_orbit * factor,
             "checks": W_MARGIN * s_margin * factor, "brightness": W_BRIGHT * s_bright * factor}
    return {"score": round(sum(parts.values()), 4),
            "score_parts": {k: round(v, 4) for k, v in parts.items()},
            "detail": {"terms": {"snr": round(s_snr, 3), "transits": round(s_orbit, 3), "checks": round(s_margin, 3),
                                 "brightness": round(s_bright, 3)},
                       "weights": {"snr": W_SNR, "transits": W_TRANSITS, "checks": W_MARGIN, "brightness": W_BRIGHT},
                       "kind": kind, "kind_factor": KIND_FACTOR[kind],
                       "single_sector_factor": SINGLE_SECTOR_FACTOR if single_sector else 1.0,
                       "formula": "K_kind * (0.40*S_snr + 0.20*S_transits + 0.25*S_checks + 0.15*S_brightness)"
                                  " * (0.8 if single-sector); K = 1 periodic, 0.5 duo, 0.3 single; for a duo "
                                  "S_transits = 1/(surviving aliases), for a single 0; each part = weight * S * K"}}


def score(sig: Signal, checks: list[chk.Check], tmag: float | None, single_sector: bool) -> dict:
    """Periodic score on 0-1 plus the contribution of each part (they sum to the score)."""
    s_tr = 1 - math.exp(-max(sig.n_transits - MIN_TRANSITS, 0) / 6)
    return _score("periodic", sig.snr, s_tr, checks, tmag, single_sector, MIN_SNR)


def dip_score(res: sg.DipResult, tmag: float | None) -> dict:
    s_orbit = 1 / len(res.aliases) if res.kind == "duo" and res.aliases else 0.0
    need = sg.SINGLE_MIN_SNR if res.kind == "single" else sg.DUO_MIN_SNR
    return _score(res.kind, res.snr, s_orbit, res.checks, tmag, False, need)


def first_failed_stage(sig: Signal, failed_checks: list[str], known: dict | None) -> str | None:
    if sig.snr < MIN_SNR:
        return "snr"
    if sig.sde < MIN_SDE:
        return "sde"
    if sig.n_transits < MIN_TRANSITS:
        return "transits"
    if failed_checks:
        return "checks"
    if known is not None and known["same_star"]:
        return "known"
    if known is not None and known["neighbours"]:
        return "neighbour"
    return None


def dip_failed_stage(res: sg.DipResult, known: dict | None) -> str | None:
    snr = next(c for c in res.checks if c.name == "snr")
    if snr.passed is False:
        return "snr"
    if res.failed:
        return "checks"
    if known is not None and known["same_star"]:
        return "known"
    if known is not None and known["neighbours"]:
        return "neighbour"
    return None


def _unfolded(t: np.ndarray, f: np.ndarray) -> dict:
    """Binned light curve over time: 30-min bins, wider when that would exceed UNFOLDED_MAX_POINTS (stitched
    curves of dozens of sectors)."""
    days = len(np.unique(np.floor(t * 2))) / 2 if len(t) else 0.0
    minutes = max(30.0, math.ceil(days * 1440 / UNFOLDED_MAX_POINTS / 10) * 10)
    bt, bf, _ = bin_by_time(t, f, minutes / 1440)
    return {"time_btjd": [round(float(x), 5) for x in bt], "flux": [round(float(x), 6) for x in bf],
            "bin_minutes": minutes}


def _zoom(t: np.ndarray, f: np.ndarray, hours: np.ndarray, span: float) -> dict:
    z = np.abs(hours) < span
    zb = np.linspace(-span, span, 61)
    zi = np.clip(np.digitize(hours[z], zb) - 1, 0, 59)
    zc, zs = np.bincount(zi, minlength=60), np.bincount(zi, weights=f[z], minlength=60)
    ok = zc > 0
    return {"hours_from_mid": [round(float(x), 4) for x in (0.5 * (zb[:-1] + zb[1:]))[ok]],
            "flux": [round(float(x), 6) for x in zs[ok] / zc[ok]]}


def curves(t: np.ndarray, f: np.ndarray, sig: Signal) -> dict:
    """Binned folded curve (full orbit and a zoom on the transit) and binned unfolded curve."""
    phase = ((t - sig.t0) / sig.period + 0.5) % 1.0 - 0.5
    order = np.argsort(phase)
    nb = 200
    edges = np.linspace(-0.5, 0.5, nb + 1)
    idx = np.clip(np.digitize(phase[order], edges) - 1, 0, nb - 1)
    cnt = np.bincount(idx, minlength=nb)
    fsum = np.bincount(idx, weights=f[order], minlength=nb)
    ok = cnt > 0
    centres = 0.5 * (edges[:-1] + edges[1:])
    return {
        "folded": {"phase": [round(float(x), 5) for x in centres[ok]],
                   "flux": [round(float(x), 6) for x in fsum[ok] / cnt[ok]], "bins": nb},
        "folded_zoom": _zoom(t, f, phase * sig.period * 24, 3 * sig.duration * 24),
        "unfolded": _unfolded(t, f),
    }


def dip_curves(t: np.ndarray, f: np.ndarray, res: sg.DipResult) -> dict:
    """For single / duo: no fold over an orbit for a single (folded = None); folded_zoom stacks the dips on their
    mid-times; dip_curves has each dip on its own; a duo is also folded at its most probable period."""
    span = 3 * res.duration * 24
    hours = np.full(len(t), np.inf)
    for e in res.events:
        h = (t - e.tc) * 24
        hours = np.where(np.abs(h) < np.abs(hours), h, hours)
    out = {"folded": None, "folded_zoom": _zoom(t, f, hours, span), "unfolded": _unfolded(t, f),
           "dip_curves": [{"mid_btjd": round(e.tc, 5), **_zoom(t, f, (t - e.tc) * 24, span)} for e in res.events]}
    if res.kind == "duo" and res.period.median:
        p = res.period.median
        fake = Signal(p, res.events[0].tc, res.duration, res.depth, res.depth_err, res.snr, 0.0, 2, 0, 0, 0, 0)
        out["folded"] = curves(t, f, fake)["folded"]
    return out


@dataclass
class StarResult:
    tic: int
    list: str
    star: dict
    sectors: list[int]
    products: list[dict]
    masked_known: list[dict]
    signals: list[dict]  # every periodic signal examined, compact, with the stage it failed at
    candidates: list[dict]  # full candidate records (with curves), every kind
    error: str | None = None
    timings_s: dict = field(default_factory=dict)
    dips: list[dict] = field(default_factory=list)  # every single / duo examined, compact, with its stage
    events: list[dict] = field(default_factory=list)  # every dip >= singles.EVENT_MIN_SES (for merge's neighbour test)
    stitch: dict = field(default_factory=dict)
    search: dict = field(default_factory=dict)  # what ran: BLS / TLS coverage, windows

    def summary(self) -> dict:
        return {"tic": self.tic, "list": self.list, "star": self.star, "sectors": self.sectors,
                "products": self.products, "masked_known": self.masked_known, "signals": self.signals,
                "dips": self.dips, "events": self.events, "stitch": self.stitch, "search": self.search,
                "n_candidates": len(self.candidates), "error": self.error,
                "timings_s": {k: round(v, 2) for k, v in self.timings_s.items()}}


def _is_real_periodic(sig: Signal, checks: list[chk.Check]) -> bool:
    """Masked before the dip search: strong enough and not resting on one dip."""
    three = next((c for c in checks if c.name == "three_dips"), None)
    return sig.snr >= CONTINUE_MIN_SNR and three is not None and three.passed is True


def analyse(star: Star, lc: StarLC, catalogue: Catalogue | None, list_kind: str = "A",
            max_signals: int = 3, check_known: bool = True, deep_search: bool = True,
            dip_search: bool = True, tls_budget_s: float | None = None) -> StarResult:
    import time as _t

    from .deep import TLS_BUDGET_S

    t_start = _t.perf_counter()
    budget = TLS_BUDGET_S if tls_budget_s is None else tls_budget_s
    known_here = catalogue.on_star(star.tic) if (catalogue is not None and list_kind == "B") else []
    premask, masked = known_transit_mask(lc.time, lc.flux, known_here)
    out = find_signals(lc, premask, max_signals, star=star, deep_search=deep_search, tls_budget_s=budget)
    tls_spent = out.runtime.get("tls_s", 0.0)
    # Safety net for sibling searches: a signal at a listed period on this star is the known planet leaking
    # through its ephemeris mask (strong TTVs, a drifted period). Mask it where the data put it and search again.
    for _ in range(MAX_LEAK_ROUNDS):
        leaks = [(s, catalogue.match(star.tic, s.period)["same_star"]) for s in out.signals
                 if known_here and s.snr >= CONTINUE_MIN_SNR]
        leaks = [(s, m) for s, m in leaks if m]
        if not leaks:
            break
        for s, m in leaks:
            leak = in_transit(lc.time, s.period, s.t0, s.duration, scale=2.0)
            premask = premask | leak
            masked.append(MaskedPlanet(f"{m[0]['name']} (as found in the data)", s.period, s.t0, s.duration,
                                       int(leak.sum()), "leaked through the catalogue-ephemeris mask; masked at "
                                       "the period and epoch the search found"))
        out = find_signals(lc, premask, max_signals, star=star, deep_search=deep_search,
                           tls_budget_s=max(budget - tls_spent, 0.0))  # one TLS budget per star
        tls_spent += out.runtime.get("tls_s", 0.0)
    t_periodic = _t.perf_counter()
    t_all, g_all = lc.time, lc.sector
    stitch = lc.stitch_info()
    records, cands = [], []
    dip_mask = premask.copy()
    for n, sig in enumerate(out.signals, start=1):
        flat_i, use_i = out.vetting_curve(n - 1)
        use = use_i.copy()
        for o in out.signals:  # vet without the other real signals' dips (noise-level ones would cut out data)
            if o is not sig and o.snr >= CONTINUE_MIN_SNR:
                use &= ~in_transit(t_all, o.period, o.t0, o.duration, scale=1.5)
        t, f, g = t_all[use], flat_i[use], g_all[use]
        checks, extra = chk.run_all(t, f, g, sig, star, lc.dumps, lc.flagged, lc.quality_read)
        failed = chk.failures(checks)
        known = catalogue.match(star.tic, sig.period, star.ra, star.dec) if (catalogue and check_known) else None
        stage = first_failed_stage(sig, failed, known)
        single = len(extra["sectors_with_transits"]) <= 1
        sc = score(sig, checks, star.tmag, single)
        method = out.methods[n - 1] if n - 1 < len(out.methods) else {"kept": "bls_short", "found_by": ["bls_short"]}
        if _is_real_periodic(sig, checks):
            dip_mask |= in_transit(t_all, sig.period, sig.t0, sig.duration, scale=2.0)
        rec = {"n": n, "kind": "periodic", "period_d": round(sig.period, 6), "t0_btjd": round(sig.t0, 5),
               "duration_h": round(sig.duration * 24, 3), "depth_ppm": round(sig.depth * 1e6, 1),
               "snr": round(sig.snr, 2), "sde": round(sig.sde, 2), "n_transits": sig.n_transits,
               "failed_stage": stage, "failed_checks": failed,
               "failed_reasons": {c.name: c.reason for c in checks if c.name in failed},
               "known_status": None if known is None else known["status"],
               "known_names": [] if known is None else [m["name"] for m in known["same_star"] + known["neighbours"]],
               "score": sc["score"], "found_by": method.get("found_by"), "kept": method.get("kept")}
        records.append(rec)
        if stage is None:
            cands.append(candidate(star, lc, sig, n, checks, extra, known, sc, list_kind, masked, t, f,
                                   stitch=stitch, method=method))
    t_vet = _t.perf_counter()

    dip_records, events_out, dip_info = [], [], {}
    if dip_search:
        # Dips last >= 1 h: search them on the 10-min binned copy (fast), masks carried over from the native curve.
        lcd = bin_lc(lc, BIN_MINUTES) if lc.bin_minutes is None else lc
        near = np.clip(np.searchsorted(lc.time, lcd.time), 0, len(lc.time) - 1)
        dmask = dip_mask[near] | dip_mask[np.clip(near - 1, 0, len(lc.time) - 1)]
        events, results, dip_info = sg.search(star, lcd, dmask)
        events_out = [{**e.to_dict(), "failed_checks": e.failed(),
                       "rejected_because": {c.name: c.reason for c in e.checks if c.passed is False}}
                      for e in events]
        for m, res in enumerate(results, start=1):
            times = [e.tc for e in res.events]
            known = (catalogue.match_times(star.tic, times, res.duration, star.ra, star.dec,
                                           [a["period_d"] for a in res.aliases]) if (catalogue and check_known)
                     else None)
            stage = dip_failed_stage(res, known)
            sc = dip_score(res, star.tmag)
            rec = {"n": m, "kind": res.kind, "mid_times_btjd": [round(x, 5) for x in times],
                   "duration_h": round(res.duration * 24, 3), "depth_ppm": round(res.depth * 1e6, 1),
                   "snr": round(res.snr, 2), "period_d": _period_value(res),
                   "period_range_d": _range(res), "n_aliases": len(res.aliases) if res.kind == "duo" else None,
                   "failed_stage": stage, "failed_checks": res.failed,
                   "known_status": None if known is None else known["status"],
                   "known_names": [] if known is None else [x["name"] for x in known["same_star"] + known["neighbours"]],
                   "score": sc["score"]}
            dip_records.append(rec)
            if stage is None:
                cands.append(dip_candidate(star, lc, res, m, known, sc, list_kind, masked, lcd.time[~dmask],
                                           _dip_flat(lcd, dmask, res), stitch))
    t_end = _t.perf_counter()
    search_info = {"periodic": {"runtime": {k: (round(v, 2) if isinstance(v, float) else v)
                                            for k, v in out.runtime.items()},
                                "long_window_d": None if out.long_window_d is None else round(out.long_window_d, 3),
                                "deep": deep_search},
                   "dips": dip_info}
    res = StarResult(star.tic, list_kind, star.to_row(), lc.sectors,
                     [{k: p[k] for k in ("sector", "author", "exptime")} for p in lc.products],
                     [m.to_dict() for m in masked], records, cands, dips=dip_records, events=events_out,
                     stitch=stitch, search=search_info)
    res.timings_s = {"periodic": t_periodic - t_start, "vetting": t_vet - t_periodic, "dips": t_end - t_vet,
                     **{k: v for k, v in out.runtime.items() if k.endswith("_s")}}
    return res


def _dip_flat(lc: StarLC, mask: np.ndarray, res: sg.DipResult) -> np.ndarray:
    from . import detrend

    window = 3 * max(res.duration, 4 / 24)
    dips = np.zeros(len(lc.time), bool)
    for e in res.events:
        dips |= np.abs(lc.time - e.tc) < 0.75 * e.duration
    flat, _ = detrend.flatten(lc.time, lc.flux, window, mask | dips)
    return flat[~mask]


def _period_value(res: sg.DipResult) -> float | None:
    if res.kind == "single" or res.period.median is None:
        return None
    return round(res.period.median, 5)


def _range(res: sg.DipResult) -> list[float] | None:
    if res.period.lo is None:
        return None
    return [round(res.period.lo, 3), round(res.period.hi, 3)]


def _radius_fields(extra: dict) -> dict:
    lo, hi = extra["radius_lower_rjup"], extra["radius_upper_rjup"]
    return {
        "radius_rjup": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "radius_low": None if lo is None else round(lo, 4),  # the same range as plain numbers (FINDER-API)
        "radius_high": None if hi is None else round(hi, 4),
        "radius_rjup_best": None if extra["radius_rjup"] is None else round(extra["radius_rjup"], 4),
        "radius_rearth_best": None if extra["radius_rearth"] is None else round(extra["radius_rearth"], 2),
    }


def candidate(star: Star, lc: StarLC, sig: Signal, n: int, checks: list[chk.Check], extra: dict, known: dict | None,
              sc: dict, list_kind: str, masked, t: np.ndarray, f: np.ndarray, stitch: dict | None = None,
              method: dict | None = None) -> dict:
    stitch = stitch or lc.stitch_info()
    dur_h = round(sig.duration * 24, 3)
    dips = [{"mid_btjd": tt, "depth_ppm": d, "depth_err_ppm": e, "duration_h": dur_h}
            for tt, d, e in zip(extra["transit_times_btjd"], extra["transit_depths_ppm"],
                                extra.get("transit_depth_errs_ppm", [None] * len(extra["transit_times_btjd"])))]
    return {
        "id": f"hunt:{star.tic}:{n}",
        "tic": star.tic,
        "status": "candidate",
        "kind": "periodic",
        "note": NOTE,
        "period_d": round(sig.period, 6),
        "period_range_d": None,
        "period_aliases_d": None,
        "t0_btjd": round(sig.t0, 5),
        "duration_h": dur_h,
        "depth_ppm": round(sig.depth * 1e6, 1),
        "depth_err_ppm": round(sig.depth_err * 1e6, 1),
        "snr": round(sig.snr, 2),
        "sde": round(sig.sde, 2),
        "n_transits": sig.n_transits,
        "dips": dips,
        "sectors": lc.sectors,
        "sectors_used": stitch["sectors_used"],
        "baseline_d": stitch["baseline_d"],
        "stitch": stitch,
        "sectors_with_transits": extra["sectors_with_transits"],
        **_radius_fields(extra),
        "checks": [c.to_dict() for c in checks],
        "single_sector_only": len(extra["sectors_with_transits"]) <= 1,
        "per_sector_depth": extra["per_sector"],
        "transit_times_btjd": extra["transit_times_btjd"],
        "score": sc["score"],
        "score_parts": sc["score_parts"],
        "score_detail": sc["detail"],
        "known_lists": known,
        "search_list": {"A": "new-star search", "B": "sibling search on a known host"}.get(list_kind, list_kind),
        "found_by": (method or {}).get("found_by", ["bls_short"]),
        "search": method or {"kept": "bls_short", "found_by": ["bls_short"]},
        "masked_known_planets": [m.to_dict() for m in masked],
        "star": star.to_row(),
        "data": [{k: p[k] for k in ("sector", "author", "exptime")} for p in lc.products],
        **curves(t, f, sig),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def dip_candidate(star: Star, lc: StarLC, res: sg.DipResult, m: int, known: dict | None, sc: dict,
                  list_kind: str, masked, t: np.ndarray, f: np.ndarray, stitch: dict) -> dict:
    e0 = res.events[0]
    per_sector = {int(e.sector): {"depth_ppm": round(e.depth * 1e6, 1), "err_ppm": round(e.depth_err * 1e6, 1),
                                  "n_transits": 1} for e in res.events}
    aliases = [{"period_d": round(float(a["period_d"]), 5), "n": a["n"], "weight": round(a.get("weight", 0.0), 4),
                "duration_fit": round(a.get("duration_fit", 0.0), 4), "extra_dips": a["extra_dips"]}
               for a in res.aliases]
    return {
        "id": f"hunt:{star.tic}:{res.kind[0]}{m}",
        "tic": star.tic,
        "status": "candidate",
        "kind": res.kind,
        "note": NOTE + DIP_NOTE[res.kind],
        "period_d": _period_value(res),
        "period_range_d": _range(res),
        "period_range_detail": {"method": res.period.detail.get("method"),
                                "percentiles": "5-95%" if res.kind == "single" else "shortest-longest surviving alias",
                                "median_d": None if res.period.median is None else round(res.period.median, 3),
                                **{k: v for k, v in res.period.detail.items() if k != "method"}},
        "period_aliases_d": [a["period_d"] for a in aliases] if res.kind == "duo" else None,
        "period_aliases": aliases if res.kind == "duo" else None,
        "t0_btjd": round(e0.tc, 5),
        "duration_h": round(res.duration * 24, 3),
        "depth_ppm": round(res.depth * 1e6, 1),
        "depth_err_ppm": round(res.depth_err * 1e6, 1),
        "snr": round(res.snr, 2),
        "sde": None,
        "n_transits": len(res.events),
        "dips": [e.to_dict() for e in res.events],
        "sectors": lc.sectors,
        "sectors_used": stitch["sectors_used"],
        "baseline_d": stitch["baseline_d"],
        "stitch": stitch,
        "sectors_with_transits": sorted({int(e.sector) for e in res.events}),
        **_radius_fields(res.extra),
        "checks": [c.to_dict() for c in res.checks],
        "single_sector_only": len({e.sector for e in res.events}) <= 1,
        "per_sector_depth": per_sector,
        "transit_times_btjd": [round(e.tc, 5) for e in res.events],
        "score": sc["score"],
        "score_parts": sc["score_parts"],
        "score_detail": sc["detail"],
        "known_lists": known,
        "search_list": {"A": "new-star search", "B": "sibling search on a known host"}.get(list_kind, list_kind),
        "found_by": ["dip_search"],
        "search": {"kept": "dip_search", "found_by": ["dip_search"]},
        "masked_known_planets": [x.to_dict() for x in masked],
        "star": star.to_row(),
        "data": [{k: p[k] for k in ("sector", "author", "exptime")} for p in lc.products],
        **dip_curves(t, f, res),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def plot_candidate(cand: dict, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c = cand
    kind = c.get("kind", "periodic")
    fig, axes = plt.subplots(3, 1, figsize=(9, 9))
    u = c["unfolded"]
    axes[0].plot(u["time_btjd"], u["flux"], ".", ms=2, color="0.3")
    for tt in cand["transit_times_btjd"]:
        axes[0].axvline(tt, color="tab:red", alpha=0.3, lw=0.8)
    axes[0].set_xlabel("time [BTJD]")
    axes[0].set_ylabel(f"flux ({u.get('bin_minutes', 30):.0f}-min bins)")
    if c.get("folded"):
        fo = c["folded"]
        axes[1].plot(fo["phase"], fo["flux"], ".", color="0.2")
        axes[1].set_xlabel("orbital phase" + (" (most probable alias)" if kind == "duo" else ""))
        axes[1].set_ylabel("flux (folded)")
    else:
        for dc in c.get("dip_curves", []):
            axes[1].plot(dc["hours_from_mid"], dc["flux"], ".-", ms=3, lw=0.5, label=f"BTJD {dc['mid_btjd']:.2f}")
        axes[1].set_xlabel("hours from the dip's mid-time")
        axes[1].set_ylabel("flux")
        axes[1].legend(fontsize=8)
    z = c["folded_zoom"]
    axes[2].plot(z["hours_from_mid"], z["flux"], "o", ms=3, color="tab:blue")
    d = cand["depth_ppm"] * 1e-6
    h = cand["duration_h"] / 2
    axes[2].plot([-3 * h * 2, -h, -h, h, h, 3 * h * 2], [1, 1, 1 - d, 1 - d, 1, 1], color="tab:red", lw=1)
    axes[2].set_xlabel("hours from mid-transit")
    axes[2].set_ylabel("flux")
    r = cand["radius_rjup"]
    size = f"R = {r[0]:.3f}-{r[1]:.3f} R_Jup" if None not in r else "R unknown"
    if kind == "periodic":
        per = f"P = {cand['period_d']:.4f} d"
    elif kind == "duo":
        per = f"duo, P in {', '.join(f'{p:.1f}' for p in cand['period_aliases_d'][:4])}" + \
              ("..." if len(cand["period_aliases_d"]) > 4 else "") + " d"
    else:
        pr = cand["period_range_d"]
        per = "single, P ~ " + (f"{pr[0]:.0f}-{pr[1]:.0f} d" if pr else "unknown")
    fig.suptitle(f"TIC {cand['tic']} candidate {cand['id'].rsplit(':', 1)[1]}: {per}, depth {cand['depth_ppm']:.0f} "
                 f"ppm, SNR {cand['snr']:.1f}, {size}, score {cand['score']:.2f}", fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)

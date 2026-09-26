"""One star: mask known transits -> search -> checks -> known-list match -> filter -> score -> candidates.

Filter (a signal must pass every stage, in this order; the first stage it fails is recorded for the funnel):
  snr       SNR >= 10
  sde       SDE >= 9
  transits  >= 3 transits with data
  checks    no check failed, and every must-run check actually ran (checks.MUST_RUN)
  known     period does not match (1% or x2, x3, 1/2, 1/3) a confirmed planet, TOI, CTOI or catalogued EB on
            this star
  neighbour ... nor on a listed star within 2.5 arcmin (likely the source of the dips)

Score (0-100, transparent):
  score = 100 * (0.40 * S_snr + 0.20 * S_transits + 0.25 * S_margin + 0.15 * S_bright) * (0.8 if single-sector)
  S_snr      = 1 - exp(-(SNR - 10) / 20)            0 at the SNR cut, 0.63 at SNR 30
  S_transits = 1 - exp(-(N - 3) / 6)                0 at 3 transits, 0.63 at 9
  S_margin   = mean check margin (odd_even, secondary_eclipse, size, period_alias, momentum_dump,
               sector_depth, duration), each 0 at its threshold and 1 far inside it
  S_bright   = clip((13 - Tmag) / 5, 0, 1)          0 at Tmag 13, 1 at Tmag 8 (follow-up is easier)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import UTC, datetime

import numpy as np

from hunter.search import Signal, bin_by_time, in_transit

from . import checks as chk
from .catalogs import Catalogue
from .lightcurve import StarLC
from .signals import CONTINUE_MIN_SNR, find_signals, known_transit_mask
from .stars import Star

MIN_SNR = 10.0
MIN_SDE = 9.0
MIN_TRANSITS = 3
STAGES = ("snr", "sde", "transits", "checks", "known", "neighbour")
SINGLE_SECTOR_FACTOR = 0.8
W_SNR, W_TRANSITS, W_MARGIN, W_BRIGHT = 0.40, 0.20, 0.25, 0.15


def score(sig: Signal, checks: list[chk.Check], tmag: float | None, single_sector: bool) -> dict:
    s_snr = 1 - math.exp(-max(sig.snr - MIN_SNR, 0) / 20)
    s_tr = 1 - math.exp(-max(sig.n_transits - MIN_TRANSITS, 0) / 6)
    margins = [c.margin for c in checks if c.margin is not None]
    s_margin = float(np.mean(margins)) if margins else 0.0
    s_bright = min(1.0, max(0.0, (13 - tmag) / 5)) if tmag is not None else 0.0
    raw = W_SNR * s_snr + W_TRANSITS * s_tr + W_MARGIN * s_margin + W_BRIGHT * s_bright
    factor = SINGLE_SECTOR_FACTOR if single_sector else 1.0
    return {"score": round(100 * raw * factor, 1),
            "terms": {"snr": round(s_snr, 3), "transits": round(s_tr, 3), "margin": round(s_margin, 3),
                      "brightness": round(s_bright, 3)},
            "weights": {"snr": W_SNR, "transits": W_TRANSITS, "margin": W_MARGIN, "brightness": W_BRIGHT},
            "single_sector_factor": factor,
            "formula": "100*(0.40*S_snr + 0.20*S_transits + 0.25*S_margin + 0.15*S_bright) * (0.8 if single-sector)"}


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

    hours = phase * sig.period * 24
    span = 3 * sig.duration * 24
    z = np.abs(hours) < span
    zb = np.linspace(-span, span, 61)
    zi = np.clip(np.digitize(hours[z], zb) - 1, 0, 59)
    zc, zs = np.bincount(zi, minlength=60), np.bincount(zi, weights=f[z], minlength=60)
    zok = zc > 0

    bt, bf, _ = bin_by_time(t, f, 30 / 1440)
    return {
        "folded": {"phase": [round(float(x), 5) for x in centres[ok]],
                   "flux": [round(float(x), 6) for x in fsum[ok] / cnt[ok]], "bins": nb},
        "folded_zoom": {"hours_from_mid": [round(float(x), 4) for x in (0.5 * (zb[:-1] + zb[1:]))[zok]],
                        "flux": [round(float(x), 6) for x in zs[zok] / zc[zok]]},
        "unfolded": {"time_btjd": [round(float(x), 5) for x in bt], "flux": [round(float(x), 6) for x in bf],
                     "bin_minutes": 30},
    }


@dataclass
class StarResult:
    tic: int
    list: str
    star: dict
    sectors: list[int]
    products: list[dict]
    masked_known: list[dict]
    signals: list[dict]  # every signal examined, compact, with the stage it failed at
    candidates: list[dict]  # full candidate records (with curves)
    error: str | None = None
    timings_s: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {"tic": self.tic, "list": self.list, "star": self.star, "sectors": self.sectors,
                "products": self.products, "masked_known": self.masked_known, "signals": self.signals,
                "n_candidates": len(self.candidates), "error": self.error,
                "timings_s": {k: round(v, 2) for k, v in self.timings_s.items()}}


def analyse(star: Star, lc: StarLC, catalogue: Catalogue | None, list_kind: str = "A",
            max_signals: int = 3, check_known: bool = True) -> StarResult:
    known_here = catalogue.on_star(star.tic) if (catalogue is not None and list_kind == "B") else []
    premask, masked = known_transit_mask(lc.time, known_here)
    out = find_signals(lc, premask, max_signals)
    t_all, g_all = lc.time, lc.sector
    records, cands = [], []
    for n, sig in enumerate(out.signals, start=1):
        use = out.use.copy()
        for o in out.signals:  # vet without the other real signals' dips (noise-level ones would cut out data)
            if o is not sig and o.snr >= CONTINUE_MIN_SNR:
                use &= ~in_transit(t_all, o.period, o.t0, o.duration, scale=1.5)
        t, f, g = t_all[use], out.flat[use], g_all[use]
        checks, extra = chk.run_all(t, f, g, sig, star, lc.dumps, lc.flagged, lc.quality_read)
        failed = chk.failures(checks)
        known = catalogue.match(star.tic, sig.period, star.ra, star.dec) if (catalogue and check_known) else None
        stage = first_failed_stage(sig, failed, known)
        single = len(extra["sectors_with_transits"]) <= 1
        sc = score(sig, checks, star.tmag, single)
        rec = {"n": n, "period_d": round(sig.period, 6), "t0_btjd": round(sig.t0, 5),
               "duration_h": round(sig.duration * 24, 3), "depth_ppm": round(sig.depth * 1e6, 1),
               "snr": round(sig.snr, 2), "sde": round(sig.sde, 2), "n_transits": sig.n_transits,
               "failed_stage": stage, "failed_checks": failed,
               "known_status": None if known is None else known["status"],
               "known_names": [] if known is None else [m["name"] for m in known["same_star"] + known["neighbours"]],
               "score": sc["score"]}
        records.append(rec)
        if stage is None:
            cands.append(candidate(star, lc, sig, n, checks, extra, known, sc, list_kind, masked, t, f))
    return StarResult(star.tic, list_kind, star.to_row(), lc.sectors,
                      [{k: p[k] for k in ("sector", "author", "exptime")} for p in lc.products],
                      [m.to_dict() for m in masked], records, cands)


def candidate(star: Star, lc: StarLC, sig: Signal, n: int, checks: list[chk.Check], extra: dict, known: dict | None,
              sc: dict, list_kind: str, masked, t: np.ndarray, f: np.ndarray) -> dict:
    lo, hi = extra["radius_lower_rjup"], extra["radius_upper_rjup"]
    return {
        "id": f"hunt:{star.tic}:{n}",
        "tic": star.tic,
        "status": "candidate",
        "note": "A planet candidate from an automated search, not a confirmed planet. It needs review by "
                "people and follow-up observations; other things, such as a faint background binary, can look "
                "the same.",
        "period_d": round(sig.period, 6),
        "t0_btjd": round(sig.t0, 5),
        "duration_h": round(sig.duration * 24, 3),
        "depth_ppm": round(sig.depth * 1e6, 1),
        "depth_err_ppm": round(sig.depth_err * 1e6, 1),
        "snr": round(sig.snr, 2),
        "sde": round(sig.sde, 2),
        "n_transits": sig.n_transits,
        "sectors": lc.sectors,
        "sectors_with_transits": extra["sectors_with_transits"],
        "radius_rjup": [None if lo is None else round(lo, 4), None if hi is None else round(hi, 4)],
        "radius_rjup_best": None if extra["radius_rjup"] is None else round(extra["radius_rjup"], 4),
        "radius_rearth_best": None if extra["radius_rearth"] is None else round(extra["radius_rearth"], 2),
        "checks": [c.to_dict() for c in checks],
        "single_sector_only": len(extra["sectors_with_transits"]) <= 1,
        "per_sector_depth": extra["per_sector"],
        "transit_times_btjd": extra["transit_times_btjd"],
        "score": sc["score"],
        "score_detail": sc,
        "known": known,
        "search_list": {"A": "new-star search", "B": "sibling search on a known host"}.get(list_kind, list_kind),
        "masked_known_planets": [m.to_dict() for m in masked],
        "star": star.to_row(),
        "data": [{k: p[k] for k in ("sector", "author", "exptime")} for p in lc.products],
        "curves": curves(t, f, sig),
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def plot_candidate(cand: dict, path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    c = cand["curves"]
    fig, axes = plt.subplots(3, 1, figsize=(9, 9))
    u = c["unfolded"]
    axes[0].plot(u["time_btjd"], u["flux"], ".", ms=2, color="0.3")
    for tt in cand["transit_times_btjd"]:
        axes[0].axvline(tt, color="tab:red", alpha=0.3, lw=0.8)
    axes[0].set_xlabel("time [BTJD]")
    axes[0].set_ylabel("flux (30-min bins)")
    fo = c["folded"]
    axes[1].plot(fo["phase"], fo["flux"], ".", color="0.2")
    axes[1].set_xlabel("orbital phase")
    axes[1].set_ylabel("flux (folded)")
    z = c["folded_zoom"]
    axes[2].plot(z["hours_from_mid"], z["flux"], "o", ms=3, color="tab:blue")
    d = cand["depth_ppm"] * 1e-6
    h = cand["duration_h"] / 2
    axes[2].plot([-3 * h * 2, -h, -h, h, h, 3 * h * 2], [1, 1, 1 - d, 1 - d, 1, 1], color="tab:red", lw=1)
    axes[2].set_xlabel("hours from mid-transit")
    axes[2].set_ylabel("flux")
    r = cand["radius_rjup"]
    size = f"R = {r[0]:.3f}-{r[1]:.3f} R_Jup" if None not in r else "R unknown"
    fig.suptitle(f"TIC {cand['tic']} candidate {cand['id'].rsplit(':', 1)[1]}: P = {cand['period_d']:.4f} d, "
                 f"depth {cand['depth_ppm']:.0f} ppm, SNR {cand['snr']:.1f}, {size}, score {cand['score']}",
                 fontsize=10)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    plt.close(fig)

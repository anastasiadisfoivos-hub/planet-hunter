"""hunt(): fetch -> clean -> search -> measure -> vet -> flares -> known check -> Discovery list."""

from __future__ import annotations

import math
import time as _time
from dataclasses import dataclass, field

import numpy as np
from astropy.time import Time

from . import known
from .classify import classify
from .clean import bin_consecutive, flatten_for_search
from .fetch import LightCurveData, fetch
from .flares import Flare, find_flares
from .measure import implied_radius
from .models import CatchType, Discovery, StarTarget, empty_cutouts
from .resolve import StarInfo, resolve
from .search import DURATIONS, Signal, harmonically_related, in_transit, search
from .vet import odd_even, secondary_eclipse, size, snr

FLATTEN_WINDOW = 3 * float(DURATIONS.max())  # 0.9 d: three times the longest transit we search for
EXTRA_SIGNAL_MIN_SNR = 10.0
EXTRA_SIGNAL_MIN_SDE = 10.0
MAX_FLARES = 50
BTJD_OFFSET = 2457000.0


@dataclass
class HuntResult:
    star: StarInfo
    discoveries: list[Discovery]
    signals: list[dict]  # every signal examined, with its vetting, including rejected ones
    flares_found: int
    products: list[dict]
    timings_s: dict[str, float] = field(default_factory=dict)
    # Kept for plotting; not serialised.
    lc: LightCurveData | None = None
    flat: np.ndarray | None = None
    keep: np.ndarray | None = None
    signal_objs: list[Signal] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "target": {"tic_id": self.star.tic_id, "query": self.star.query, "ra_deg": self.star.ra_deg,
                       "dec_deg": self.star.dec_deg, "stellar_radius_rsun": self.star.radius_rsun,
                       "teff_k": self.star.teff_k, "tmag": self.star.tmag},
            "data": [{k: p[k] for k in ("sector", "author", "exptime", "flux_column")} for p in self.products],
            "discoveries": [d.to_dict() for d in self.discoveries],
            "signals_examined": self.signals,
            "flares_found": self.flares_found,
            "timings_s": {k: round(v, 2) for k, v in self.timings_s.items()},
        }


def btjd_to_iso(btjd: float) -> str:
    return Time(btjd + BTJD_OFFSET, format="jd", scale="tdb").utc.isot[:19] + "Z"


def _first_transit(sig: Signal, t_min: float) -> float:
    return sig.t0 + math.ceil((t_min - sig.t0) / sig.period - 1e-9) * sig.period


def _links(tic_id: int, planet_name: str | None = None) -> list[dict[str, str]]:
    links = [
        {"label": "ExoFOP-TESS target page", "url": f"https://exofop.ipac.caltech.edu/tess/target.php?id={tic_id}"},
        {"label": "MAST archive", "url": "https://mast.stsci.edu/portal/Mashup/Clients/Mast/Portal.html"
                                         f"?searchQuery=TIC%20{tic_id}"},
    ]
    if planet_name:
        links.append({"label": "NASA Exoplanet Archive",
                      "url": "https://exoplanetarchive.ipac.caltech.edu/overview/" + planet_name.replace(" ", "%20")})
    return links


def _round_curve(t: np.ndarray, f: np.ndarray) -> dict[str, list[float]]:
    return {"time_btjd": [round(float(x), 5) for x in t], "flux": [round(float(x), 6) for x in f]}


def _find_signals(lc: LightCurveData, max_signals: int):
    """Two-pass search for the strongest signal (re-flatten with its transits masked), then extra signals."""
    t, f, g = lc.time, lc.flux, lc.sector
    flat, keep = flatten_for_search(t, f, FLATTEN_WINDOW)
    first = search(t[keep], flat[keep], g[keep])
    if first is None:
        return [], flat, keep
    # Second pass: the trend is re-estimated without the in-transit points, so the dips cannot drag it down.
    trend_mask = in_transit(t, first.period, first.t0, first.duration, scale=2.0)
    flat, keep = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=trend_mask)
    sig = search(t[keep], flat[keep], g[keep]) or first
    signals = [sig]

    while len(signals) < max_signals:
        masked = np.zeros(len(t), bool)
        for s in signals:
            masked |= in_transit(t, s.period, s.t0, s.duration, scale=2.0)
        flat2, keep2 = flatten_for_search(t, f, FLATTEN_WINDOW, transit_mask=masked)
        use = keep2 & ~masked
        nxt = search(t[use], flat2[use], g[use])
        if (nxt is None or nxt.snr < EXTRA_SIGNAL_MIN_SNR or nxt.sde < EXTRA_SIGNAL_MIN_SDE
                or nxt.n_transits < 3 or any(harmonically_related(nxt.period, s.period) for s in signals)):
            break
        signals.append(nxt)
    return signals, flat, keep


def _transit_discovery(star: StarInfo, lc: LightCurveData, flat, keep, sig: Signal, n: int, others: list[Signal]):
    t = lc.time
    use = keep.copy()
    for o in others:  # vet each signal without the other signals' dips in the way
        use &= ~in_transit(t, o.period, o.t0, o.duration, scale=1.5)
    sz = implied_radius(sig.depth, star.radius_rsun)
    sec_vet, sec = secondary_eclipse(t[use], flat[use], sig)
    vets = {"snr": snr(sig), "odd_even": odd_even(sig), "secondary_eclipse": sec_vet, "size": size(sz)}
    ctype, conf, explanation = classify(sig, vets)
    record = {"n": n, "signal": sig.to_dict(), "vetting": [v.to_dict() for v in vets.values()],
              "radius_rjup": None if sz.radius_rjup is None else round(sz.radius_rjup, 4),
              "type": None if ctype is None else str(ctype),
              "secondary_search": {k: round(float(v), 8) if np.isfinite(v) else None for k, v in sec.items()}}
    if ctype is None:
        return None, record

    kr = known.check(star.tic_id, sig.period, include_eb_catalogue=ctype == CatchType.eclipsing_binary)
    if kr.status == "known":
        explanation += f" This matches {kr.name} on the {kr.list_name} ({kr.alias})."
    elif kr.status == "not_on_lists":
        explanation += (" It is not on the lists we checked (confirmed planets, TOIs, community TOIs"
                        + (", TESS eclipsing binaries" if ctype == CatchType.eclipsing_binary else "") + ").")
    else:
        explanation += " We could not reach every catalogue, so whether it is already known is unchecked."

    tb, fb = bin_consecutive(t[use], flat[use], 2000)
    planet_name = kr.name if kr.list_name and "confirmed" in kr.list_name else None
    raw = {
        "tic_id": star.tic_id,
        "signal": sig.to_dict(),
        "vetting": record["vetting"],
        "radius_rjup": record["radius_rjup"],
        "stellar_radius_rsun": star.radius_rsun,
        "secondary_search": record["secondary_search"],
        "known_match": {"list": kr.list_name, "listed_period": kr.listed_period, "alias": kr.alias,
                        **kr.extra, "errors": kr.errors},
        "data": [{k: p[k] for k in ("sector", "author", "exptime")} for p in lc.products],
    }
    disc = Discovery(
        id=f"tess:{star.tic_id}:sig:{n}", type=ctype, confidence=conf, source="tess", origin="hunter-bls",
        ra_deg=star.ra_deg, dec_deg=star.dec_deg, detected_at=btjd_to_iso(_first_transit(sig, float(t.min()))),
        name_if_known=kr.name, known_status=kr.status, cutouts=empty_cutouts(),
        light_curve=_round_curve(tb, fb), explanation=explanation, links=_links(star.tic_id, planet_name), raw=raw,
    )
    return disc, record


def _flare_discovery(star: StarInfo, lc: LightCurveData, fl: Flare) -> Discovery:
    rise_min = (fl.t_peak - fl.t_start) * 1440
    decay_min = (fl.t_end - fl.t_peak) * 1440
    conf = round(0.5 + 0.4 * (1 - math.exp(-(fl.peak_sigma - 5) / 10)), 2)
    window = np.abs(lc.time - fl.t_peak) < 0.2
    tb, fb = bin_consecutive(lc.time[window], lc.flux[window], 2000)
    return Discovery(
        id=f"tess:{star.tic_id}:flare:{round(fl.t_peak, 2):.2f}", type=CatchType.flare, confidence=conf,
        source="tess", origin="hunter-flares", ra_deg=star.ra_deg, dec_deg=star.dec_deg,
        detected_at=btjd_to_iso(fl.t_peak), name_if_known=None, known_status="unchecked", cutouts=empty_cutouts(),
        light_curve=_round_curve(tb, fb),
        explanation=(f"Best guess: a stellar flare. The star brightened by {fl.amplitude * 100:.2f}% "
                     f"({fl.peak_sigma:.0f} times the noise), rising in about {rise_min:.0f} minutes and fading over "
                     f"about {decay_min:.0f} minutes. A fast rise and slower fade is the usual shape of a flare, a "
                     f"magnetic outburst on the star. Spacecraft glitches or a passing asteroid can look similar. "
                     f"We did not compare it with any flare list."),
        links=_links(star.tic_id), raw={"tic_id": star.tic_id, "flare": fl.to_dict()},
    )


def _eclipse_mask(time: np.ndarray, signals: list[Signal], records: list[dict]) -> np.ndarray:
    """Points in or near any transit/eclipse, including a detected secondary, for the flare search to skip."""
    mask = np.zeros(len(time), bool)
    for sig, rec in zip(signals, records):
        mask |= in_transit(time, sig.period, sig.t0, sig.duration, scale=3.0)
        sec = rec["secondary_search"]
        if sec["nsig"] > 3:
            mask |= in_transit(time, sig.period, sig.t0 + sec["phase"] * sig.period, sig.duration, scale=3.0)
    return mask


def run(target: StarTarget | int | str, max_sectors: int = 2, max_signals: int = 3, refresh: bool = False) -> HuntResult:
    timings: dict[str, float] = {}
    t0 = _time.perf_counter()
    star = resolve(target, refresh=refresh)
    timings["resolve"] = _time.perf_counter() - t0

    t1 = _time.perf_counter()
    lc = fetch(star.tic_id, max_sectors=max_sectors, refresh=refresh)
    timings["fetch"] = _time.perf_counter() - t1

    t2 = _time.perf_counter()
    signals, flat, keep = _find_signals(lc, max_signals)
    timings["search"] = _time.perf_counter() - t2

    t3 = _time.perf_counter()
    discoveries, records = [], []
    for n, sig in enumerate(signals, start=1):
        disc, record = _transit_discovery(star, lc, flat, keep, sig, n, [s for s in signals if s is not sig])
        records.append(record)
        if disc is not None:
            discoveries.append(disc)
    flares = sorted(find_flares(lc.time, lc.flux, _eclipse_mask(lc.time, signals, records)),
                    key=lambda f: -f.peak_sigma)
    discoveries += [_flare_discovery(star, lc, fl) for fl in flares[:MAX_FLARES]]
    timings["vet_known_flares"] = _time.perf_counter() - t3
    timings["total"] = _time.perf_counter() - t0

    return HuntResult(star, discoveries, records, len(flares), lc.products, timings, lc, flat, keep, signals)


def hunt(target: StarTarget | int | str, max_sectors: int = 2, refresh: bool = False) -> list[Discovery]:
    """Hunt one TESS star for transit-like signals and flares. Accepts StarTarget, a TIC number or a name."""
    return run(target, max_sectors=max_sectors, refresh=refresh).discoveries

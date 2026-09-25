"""planets/<slug>.atmosphere.json: measured transmission spectra from the NASA Exoplanet Archive.

When a planet crosses its star, starlight filters through its atmosphere; at wavelengths where
some molecule or atom absorbs, the planet looks bigger and the transit is deeper. The archive's
Atmospheric Spectroscopy table (TAP table `spectra`) lists every published spectrum; the data
points themselves are IPAC tables served next to the table's web viewer.

For each planet we keep the transmission spectrum with the most data points (all others are
listed in `spectra_available`) as transit depth in ppm. Depth comes from the file's transit
depth column (%), or from (Rp/Rs)^2 when only the radius ratio is given.

`detections` is always empty: the archive does not record which species each paper claims.
"""

from __future__ import annotations

import logging
import re
from itertools import pairwise

from . import sources
from .hosts import Host, tap_csv
from .net import DAY, FetchError, Net, key

log = logging.getLogger("skyspectra")
HOST = "https://exoplanetarchive.ipac.caltech.edu"
VIEWER_URL = f"{HOST}/cgi-bin/atmospheres/nph-firefly?atmospheres"
SPECTRA_QUERY = ("select pl_name, spec_type, authors, bibcode, num_datapoints, instrument, facility, "
                 "minwavelng, maxwavelng, note, spec_path from spectra where spec_type = 'Transmission'")
TTL = 30 * DAY


def slug(planet: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", planet.lower()).strip("-")


def parse_ipac(text: str) -> tuple[dict[str, str], list[dict[str, str | None]]]:
    """IPAC table -> (keywords, rows). Columns are the fixed-width fields between '|' marks."""
    keywords: dict[str, str] = {}
    bars: list[int] | None = None
    names: list[str] = []
    rows = []
    for line in text.splitlines():
        if line.startswith("\\"):
            if "=" in line:
                k, v = line[1:].split("=", 1)
                keywords[k.strip()] = v.strip()
            continue
        if line.startswith("|"):
            if bars is None:
                bars = [i for i, c in enumerate(line) if c == "|"]
                names = [line[a + 1:b].strip() for a, b in pairwise(bars)]
            continue
        if bars is None or not line.strip():
            continue
        values = [line[a + 1:b + 1].strip() if a + 1 < len(line) else "" for a, b in pairwise(bars)]
        rows.append({n: (None if v in ("", "null") else v) for n, v in zip(names, values)})
    return keywords, rows


def _f(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def to_depth(rows: list[dict]) -> tuple[dict, str] | None:
    """Rows -> ({wavelength_um, depth_ppm, err_ppm, bandwidth_um}, method), limits skipped."""
    wl, depth, err, bw = [], [], [], []
    methods = set()
    for r in rows:
        w = _f(r.get("CENTRALWAVELNG"))
        if w is None:
            continue
        d, e1, e2 = _f(r.get("PL_TRANDEP")), _f(r.get("PL_TRANDEPERR1")), _f(r.get("PL_TRANDEPERR2"))
        if d is not None and r.get("PL_TRANDEPLIM") in (None, "0"):
            ppm = d * 1e4
            e = [abs(x) for x in (e1, e2) if x is not None]
            eppm = sum(e) / len(e) * 1e4 if e else None
            methods.add("transit depth")
        else:
            k, k1, k2 = _f(r.get("PL_RATROR")), _f(r.get("PL_RATRORERR1")), _f(r.get("PL_RATRORERR2"))
            if k is None or r.get("PL_RATRORLIM") not in (None, "0"):
                continue
            ppm = k * k * 1e6
            e = [abs(x) for x in (k1, k2) if x is not None]
            eppm = 2 * k * (sum(e) / len(e)) * 1e6 if e else None
            methods.add("(Rp/Rs)^2")
        wl.append(round(w, 5))
        depth.append(round(ppm, 2))
        err.append(round(eppm, 2) if eppm is not None else None)
        bw.append(_f(r.get("BANDWIDTH")))
    if not wl:
        return None
    order = sorted(range(len(wl)), key=wl.__getitem__)
    pick = lambda xs: [xs[i] for i in order]
    return ({"wavelength_um": pick(wl), "depth_ppm": pick(depth), "err_ppm": pick(err),
             "bandwidth_um": pick(bw)}, " and ".join(sorted(methods)))


class SpectrumFiles:
    """The spectrum files live under a per-visit workspace path that the viewer page hands out."""

    def __init__(self, net: Net) -> None:
        self.net = net
        self._workspace: str | None = None

    def workspace(self) -> str:
        if self._workspace is None:
            page = self.net.text(VIEWER_URL, ttl=0)
            m = re.search(r"/workspace/TMP_[A-Za-z0-9_]+", page)
            if not m:
                raise ValueError("archive atmospheres viewer page has no workspace path")
            self._workspace = m.group()
        return self._workspace

    def get(self, spec_path: str) -> str:
        ck = key("nea-spectrum", spec_path)
        hit = self.net.cached(ck, TTL)  # a warm cache needs no viewer visit
        if hit is not None:
            return hit
        url = f"{HOST}{self.workspace()}/atmospheres/tab1/data/{spec_path}"
        return self.net.text(url, ttl=TTL, cache_key=ck)


def _meta_entry(row: dict) -> dict:
    return {
        "reference": row["authors"], "bibcode": row["bibcode"] or None,
        "instrument": row["instrument"], "facility": row["facility"],
        "num_datapoints": int(row["num_datapoints"] or 0),
        "min_um": _f(row["minwavelng"]), "max_um": _f(row["maxwavelng"]),
        "note": row["note"] or None, "spec_path": row["spec_path"],
    }


def build_atmospheres(net: Net, hosts: list[Host], planets: list[str] | None = None) -> dict[str, dict]:
    """slug -> atmosphere document for every planet of `hosts` with a transmission spectrum."""
    planet_host = {p: h for h in hosts for p in h.planets}
    by_planet: dict[str, list[dict]] = {}
    for row in tap_csv(net, SPECTRA_QUERY, ttl=7 * DAY):
        name = row["pl_name"]
        if name in planet_host and (planets is None or name in planets):
            by_planet.setdefault(name, []).append(row)
    files = SpectrumFiles(net)
    docs = {}
    for name, rows in sorted(by_planet.items()):
        rows.sort(key=lambda r: (-int(r["num_datapoints"] or 0), r["bibcode"] or ""))
        spectrum = None
        for row in rows:
            try:
                _, data = parse_ipac(files.get(row["spec_path"]))
            except (FetchError, ValueError) as exc:
                log.warning("%s: spectrum file %s unavailable (%s)", name, row["spec_path"], exc)
                continue
            got = to_depth(data)
            if got:
                spec, method = got
                spectrum = {**spec, "depth_from": method, **_meta_entry(row)}
                break
        h = planet_host[name]
        docs[slug(name)] = {
            "planet": name,
            "host": h.name,
            "tic": h.tic,
            "detections": [],
            "detections_note": ("The NASA Exoplanet Archive does not list detected species; see each "
                                "spectrum's reference for the authors' interpretation."),
            "spectrum": spectrum,
            "spectra_available": [_meta_entry(r) for r in rows],
            **sources.meta("nea"),
        }
    return docs

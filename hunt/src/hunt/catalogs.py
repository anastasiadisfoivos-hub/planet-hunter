"""Known-signal lists, downloaded in bulk and matched locally.

Lists: NASA Exoplanet Archive confirmed planets (pscomppars), the TOI table, ExoFOP community TOIs (CTOIs)
and the TESS eclipsing-binary catalogue (Prsa et al. 2022). Every entry keeps its ephemeris so known
transits can be masked before a sibling search.

A found signal is "known" when its period matches a listed period on the same star within 1% (or a ×2, ×3,
½, ⅓ alias, as the pipeline does). A match on a listed star within NEIGHBOUR_ARCMIN is reported too: a
bright neighbour's eclipses leak into TESS's 21-arcsecond pixels, so it is the likely source.
"""

from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from hunter.known import match_period

from .cache import DAY, cached_json, download

ARCHIVE_TAP = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
CTOI_URL = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=pipe"
VIZIER_ASU = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
EB_CATALOGUE = "J/ApJS/258/16/tess-ebs"
TTL = 1 * DAY  # TOIs are added most weeks; a nightly sweep should see yesterday's list
BJD_OFFSET = 2457000.0
NEIGHBOUR_ARCMIN = 2.5  # ~7 TESS pixels

LIST_NAMES = {
    "confirmed": "NASA Exoplanet Archive (confirmed)",
    "toi": "TESS Objects of Interest",
    "ctoi": "ExoFOP community TOIs",
    "eb": "TESS Eclipsing Binary catalogue (Prsa et al. 2022)",
}


@dataclass
class KnownSignal:
    tic: int
    name: str
    kind: str  # confirmed | toi | ctoi | eb
    period: float | None
    period_err: float | None
    t0_btjd: float | None
    t0_err: float | None
    duration_h: float | None
    ra: float | None
    dec: float | None
    disposition: str | None = None
    tmag: float | None = None
    ttv_flag: bool = False  # archive flags transit-timing variations (confirmed planets only)

    @property
    def list_name(self) -> str:
        return LIST_NAMES[self.kind]


def _f(x) -> float | None:
    try:
        v = float(str(x).strip())
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _btjd(x) -> float | None:
    v = _f(x)
    if v is None:
        return None
    return v - BJD_OFFSET if v > 2_400_000 else v


def _tap_rows(query: str, name: str, refresh: bool) -> list[dict]:
    path = download(ARCHIVE_TAP, f"catalogs/{name}.csv", TTL, refresh, params={"query": query, "format": "csv"})
    return list(csv.DictReader(io.StringIO(path.read_text())))


def _confirmed(refresh: bool) -> list[KnownSignal]:
    rows = _tap_rows("select pl_name,tic_id,hostname,pl_orbper,pl_orbpererr1,pl_tranmid,pl_tranmiderr1,pl_trandur,"
                     "ra,dec,sy_pnum,tran_flag,sy_tmag,st_teff,st_rad,ttv_flag from pscomppars where tic_id is not null",
                     "pscomppars-v2", refresh)
    out = []
    for r in rows:
        tic = r["tic_id"].replace("TIC", "").strip()
        if not tic.isdigit():
            continue
        out.append(KnownSignal(int(tic), r["pl_name"], "confirmed", _f(r["pl_orbper"]), _f(r["pl_orbpererr1"]),
                               _btjd(r["pl_tranmid"]), _f(r["pl_tranmiderr1"]), _f(r["pl_trandur"]),
                               _f(r["ra"]), _f(r["dec"]), "transiting" if r["tran_flag"] == "1" else "non-transiting",
                               _f(r["sy_tmag"]), r.get("ttv_flag") == "1"))
    return out


def _tois(refresh: bool) -> list[KnownSignal]:
    rows = _tap_rows("select tid,toi,pl_orbper,pl_orbpererr1,pl_tranmid,pl_tranmiderr1,pl_trandurh,ra,dec,"
                     "tfopwg_disp,st_tmag from toi", "toi", refresh)
    return [KnownSignal(int(r["tid"]), f"TOI-{r['toi']}", "toi", _f(r["pl_orbper"]), _f(r["pl_orbpererr1"]),
                        _btjd(r["pl_tranmid"]), _f(r["pl_tranmiderr1"]), _f(r["pl_trandurh"]), _f(r["ra"]),
                        _f(r["dec"]), r["tfopwg_disp"] or None, _f(r["st_tmag"]))
            for r in rows if r["tid"].strip().isdigit()]


def _ctois(refresh: bool) -> list[KnownSignal]:
    path = download(CTOI_URL, "catalogs/ctoi.psv", TTL, refresh)
    out = []
    for r in csv.DictReader(io.StringIO(path.read_text()), delimiter="|"):
        if not r["TIC ID"].strip().isdigit():
            continue
        out.append(KnownSignal(int(r["TIC ID"]), f"CTOI {r['CTOI']}", "ctoi", _f(r["Period (days)"]),
                               _f(r["Period (days) Error"]), _btjd(r["Transit Epoch (BJD)"]),
                               _f(r["Transit Epoch (BJD) err"]), _f(r["Duration (hrs)"]), _f(r["RA"]), _f(r["Dec"]),
                               r["TFOPWG Disposition"] or r["User Disposition"] or None, _f(r["TESS Mag"])))
    return out


def _ebs(refresh: bool) -> list[KnownSignal]:
    path = download(VIZIER_ASU, "catalogs/tess-ebs.tsv", 30 * DAY, refresh, params={
        "-source": EB_CATALOGUE, "-out.max": "unlimited",
        "-out": "TIC,RAJ2000,DEJ2000,Tmag,BJD0,e_BJD0,Per,e_Per,Morph,Wp-pf,Wp-2g"})
    lines = [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.startswith("#")]
    header = [c.strip() for c in lines[0].split("\t")]
    out = []
    for ln in lines[3:]:  # header, units, dashes, then data
        r = dict(zip(header, (c.strip() for c in ln.split("\t"))))
        if not r.get("TIC", "").isdigit():
            continue
        per = _f(r["Per"])
        width = _f(r["Wp-pf"]) or _f(r["Wp-2g"])
        out.append(KnownSignal(int(r["TIC"]), f"TIC {int(r['TIC'])} (TESS EB catalogue)", "eb", per, _f(r["e_Per"]),
                               _btjd(r["BJD0"]), _f(r["e_BJD0"]),
                               width * per * 24 if width and per else None, _f(r["RAJ2000"]), _f(r["DEJ2000"]),
                               f"morph {r['Morph']}" if r.get("Morph") else None, _f(r["Tmag"])))
    return out


class Catalogue:
    def __init__(self, entries: list[KnownSignal], fetched_at: str | None = None):
        self.entries = entries
        self.fetched_at = fetched_at
        self.by_tic: dict[int, list[KnownSignal]] = {}
        for e in entries:
            self.by_tic.setdefault(e.tic, []).append(e)
        pos = [(i, e.ra, e.dec) for i, e in enumerate(entries) if e.ra is not None and e.dec is not None]
        self._pos_idx = np.array([p[0] for p in pos], dtype=int)
        self._ra = np.radians([p[1] for p in pos])
        self._dec = np.radians([p[2] for p in pos])

    @property
    def tics(self) -> set[int]:
        return set(self.by_tic)

    def tics_of(self, *kinds: str) -> set[int]:
        return {e.tic for e in self.entries if e.kind in kinds}

    def on_star(self, tic: int) -> list[KnownSignal]:
        return list(self.by_tic.get(int(tic), []))

    def near(self, ra: float, dec: float, arcmin: float = NEIGHBOUR_ARCMIN) -> list[tuple[KnownSignal, float]]:
        if len(self._ra) == 0:
            return []
        r0, d0 = math.radians(ra), math.radians(dec)
        hav = (np.sin((self._dec - d0) / 2) ** 2
               + np.cos(d0) * np.cos(self._dec) * np.sin((self._ra - r0) / 2) ** 2)
        sep = np.degrees(2 * np.arcsin(np.sqrt(np.clip(hav, 0, 1)))) * 60
        close = np.flatnonzero(sep < arcmin)
        return [(self.entries[self._pos_idx[i]], float(sep[i])) for i in close]

    def match(self, tic: int, period: float, ra: float | None = None, dec: float | None = None) -> dict:
        """Known-list result for a signal: matches on the same star and on neighbours (period within 1% or alias)."""
        same = []
        for e in self.on_star(tic):
            alias = match_period(period, e.period)
            if alias:
                same.append({"name": e.name, "list": e.list_name, "listed_period_d": e.period, "alias": alias,
                             "disposition": e.disposition})
        neighbours = []
        if ra is not None and dec is not None:
            for e, sep in self.near(ra, dec):
                if e.tic == int(tic):
                    continue
                alias = match_period(period, e.period)
                if alias:
                    neighbours.append({"name": e.name, "tic": e.tic, "list": e.list_name, "listed_period_d": e.period,
                                       "alias": alias, "separation_arcmin": round(sep, 2), "tmag": e.tmag})
        on_lists = [{"name": e.name, "list": e.list_name, "period_d": e.period} for e in self.on_star(tic)]
        status = "known" if same else ("known_on_neighbour" if neighbours else "not_on_lists")
        return {"status": status, "same_star": same, "neighbours": neighbours, "other_entries_on_star": on_lists,
                "lists_checked": list(LIST_NAMES.values()), "neighbour_radius_arcmin": NEIGHBOUR_ARCMIN,
                "catalogue_fetched_at": self.fetched_at}

    def match_times(self, tic: int, times: list[float], duration_d: float, ra: float | None = None,
                    dec: float | None = None, periods: list[float] | None = None) -> dict:
        """Known-list result for single / double dips. Same star: a listed period matches one of `periods` (a
        duo's surviving aliases). Same star or neighbour: a listed signal predicts a transit or eclipse at one of
        the dip times (within half both durations + 3 sigma of its propagated timing error + 0.1 d)."""
        same, neighbours = [], []
        cands = [(e, 0.0) for e in self.on_star(tic)]
        if ra is not None and dec is not None:
            cands += [(e, sep) for e, sep in self.near(ra, dec) if e.tic != int(tic)]
        for e, sep in cands:
            hit = None
            if periods and e.tic == int(tic):
                for p in periods:
                    alias = match_period(p, e.period)
                    if alias:
                        hit = {"alias": f"a surviving period ({p:.3f} d): {alias}"}
                        break
            if hit is None and e.period and e.t0_btjd is not None:
                for t in times:
                    n = round((t - e.t0_btjd) / e.period)
                    sig_t = math.hypot(e.t0_err or 0.0, abs(n) * (e.period_err or 0.0))
                    tol = 0.5 * (duration_d + (e.duration_h or 3.0) / 24) + 3 * sig_t + 0.1
                    off = t - (e.t0_btjd + n * e.period)
                    if abs(off) < tol and 3 * sig_t < 0.25 * e.period:
                        hit = {"alias": f"its predicted transit/eclipse falls {off * 24:+.1f} h from the dip at "
                                        f"BTJD {t:.3f}"}
                        break
            if hit is None:
                continue
            row = {"name": e.name, "list": e.list_name, "listed_period_d": e.period, **hit}
            if e.tic == int(tic):
                same.append({**row, "disposition": e.disposition})
            else:
                neighbours.append({**row, "tic": e.tic, "separation_arcmin": round(sep, 2), "tmag": e.tmag})
        on_lists = [{"name": e.name, "list": e.list_name, "period_d": e.period} for e in self.on_star(tic)]
        status = "known" if same else ("known_on_neighbour" if neighbours else "not_on_lists")
        return {"status": status, "same_star": same, "neighbours": neighbours, "other_entries_on_star": on_lists,
                "lists_checked": list(LIST_NAMES.values()), "neighbour_radius_arcmin": NEIGHBOUR_ARCMIN,
                "catalogue_fetched_at": self.fetched_at}

    def to_json(self, path: Path, tics: set[int] | None = None) -> None:
        entries = [asdict(e) for e in self.entries if tics is None or e.tic in tics]
        path.write_text(json.dumps({"fetched_at": self.fetched_at, "entries": entries}, indent=0))

    @classmethod
    def from_json(cls, path: Path) -> Catalogue:
        data = json.loads(Path(path).read_text())
        return cls([KnownSignal(**e) for e in data["entries"]], data.get("fetched_at"))


def load(refresh: bool = False) -> Catalogue:
    """All four lists (cached a day; the EB catalogue a month). A list that cannot be fetched raises."""
    def build() -> dict:
        entries = _confirmed(refresh) + _tois(refresh) + _ctois(refresh) + _ebs(refresh)
        return {"fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
                "entries": [asdict(e) for e in entries]}
    data = cached_json("catalogue-v2", TTL, build, refresh)
    return Catalogue([KnownSignal(**e) for e in data["entries"]], data["fetched_at"])

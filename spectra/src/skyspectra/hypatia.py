"""stars/<tic>.abundances.json: what each host star is made of, from the Hypatia Catalog.

Hypatia compiles stellar abundances from ~300 literature catalogues. Its API (v2.2, no key)
matches any SIMBAD name, so we ask for 'TIC <id>' directly. `x_h_dex` is Hypatia's median
[X/H] over the catalogues (Lodders et al. 2009 solar normalisation; for Fe it is [Fe/H]);
`err_dex` is Hypatia's `plusminus`: half the spread when several catalogues measured it, else
a representative error. Species are neutral atoms (Hypatia also lists some ions separately).
"""

from __future__ import annotations

import logging

from . import sources
from .hosts import Host
from .net import DAY, Net

log = logging.getLogger("skyspectra")
API = "https://hypatiacatalog.com/hypatia/api/v2"
STAR_BATCH = 100
COMPOSITION_BATCH = 120  # GET query string stays well under 8 kB
TTL = 30 * DAY


def neutral_elements(net: Net) -> list[str]:
    return [e for e in net.json(f"{API}/element/", ttl=TTL) if "_" not in e]


def found_stars(net: Net, hosts: list[Host]) -> dict[int, dict]:
    """TIC -> Hypatia star record, for the hosts Hypatia knows."""
    found: dict[int, dict] = {}
    for i in range(0, len(hosts), STAR_BATCH):
        chunk = hosts[i:i + STAR_BATCH]
        rows = net.json(f"{API}/star/", {"name": [f"TIC {h.tic}" for h in chunk]}, ttl=TTL)
        for row in rows:
            if row.get("status") == "found":
                found[int(row["requested_name"].split()[-1])] = row
    return found


def compositions(net: Net, tics: list[int], elements: list[str]) -> dict[int, list[dict]]:
    groups = [(t, e) for t in tics for e in elements]
    out: dict[int, list[dict]] = {t: [] for t in tics}
    for i in range(0, len(groups), COMPOSITION_BATCH):
        chunk = groups[i:i + COMPOSITION_BATCH]
        if i and i % (COMPOSITION_BATCH * 50) == 0:
            log.info("  Hypatia compositions %d/%d", i, len(groups))
        rows = net.json(f"{API}/composition/", {
            "name": [f"TIC {t}" for t, _ in chunk],
            "element": [e.lower() for _, e in chunk],
        }, ttl=TTL)
        if len(rows) != len(chunk):
            raise ValueError(f"Hypatia returned {len(rows)} compositions for {len(chunk)} requests")
        for (tic, element), row in zip(chunk, rows):
            if row.get("requested_solarnorm", "lodders09") != "lodders09":
                raise ValueError(f"unexpected Hypatia solar normalisation {row.get('requested_solarnorm')}")
            if row.get("median_value") is None:
                continue
            out[tic].append({
                "symbol": element,
                "x_h_dex": row["median_value"],
                "err_dex": row.get("plusminus"),
                "n_catalogs": len(row.get("all_values") or []),
                "references": sorted({v["catalog"]["author"] for v in row.get("all_values") or []}),
            })
    return out


def build_abundances(net: Net, hosts: list[Host]) -> dict[int, dict]:
    """TIC -> abundances document, only for hosts Hypatia has at least one abundance for."""
    stars = found_stars(net, hosts)
    elements = neutral_elements(net)
    comp = compositions(net, sorted(stars), elements)
    by_tic = {h.tic: h for h in hosts}
    docs = {}
    for tic, els in comp.items():
        if not els:
            continue
        docs[tic] = {
            "tic": tic,
            "name": by_tic[tic].name,
            "hypatia_name": stars[tic].get("name"),
            **sources.meta("hypatia"),
            "solar_normalization": "Lodders et al. (2009)",
            "notation": "[X/H] in dex relative to the Sun ([Fe/H] for Fe); 0 = solar",
            "elements": els,
        }
    return docs

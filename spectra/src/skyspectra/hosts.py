"""Which stars and planets to build for: the map's exoplanet hosts, resolved via the NASA Exoplanet Archive.

`--tic-file` accepts the web map's hosts.json (an object with a "tic" list), a JSON list of TIC
ids, or plain text with one TIC id per line ('TIC 123' or '123'; '#' comments). Without it, every
host in the archive's Planetary Systems Composite table is used.
"""

from __future__ import annotations

import csv
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .net import DAY, Net

TAP_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
PS_QUERY = "select pl_name, hostname, tic_id, gaia_dr3_id from pscomppars"


@dataclass
class Host:
    tic: int
    name: str
    gaia_dr3: int | None = None
    planets: list[str] = field(default_factory=list)


def tap_csv(net: Net, query: str, ttl: float = 7 * DAY) -> list[dict]:
    text = net.text(TAP_URL, {"query": query, "format": "csv"}, ttl=ttl)
    if text.lstrip().startswith("<"):
        raise ValueError(f"archive TAP error for {query!r}: {text[:300]}")
    return list(csv.DictReader(io.StringIO(text)))


def _tic(value) -> int | None:
    """'TIC 123' / 123 / 'Gaia DR3 456' -> the id (the last number, so 'DR3' is not it)."""
    nums = re.findall(r"\d+", str(value))
    return int(nums[-1]) if nums else None


def read_tic_file(path: Path) -> list[int]:
    text = path.read_text()
    try:
        doc = json.loads(text)
    except json.JSONDecodeError:
        doc = None
    if isinstance(doc, dict) and isinstance(doc.get("tic"), list):
        values = doc["tic"]
    elif isinstance(doc, list):
        values = [v.get("tic") if isinstance(v, dict) else v for v in doc]
    elif doc is None:
        values = [ln.split("#")[0] for ln in text.splitlines()]
    else:
        raise SystemExit(f"{path}: expected hosts.json, a JSON list of TIC ids, or one TIC per line")
    tics = [t for t in (_tic(v) for v in values if str(v).strip()) if t]
    return list(dict.fromkeys(tics))


def archive_hosts(net: Net) -> dict[int, Host]:
    """TIC -> Host (name, Gaia DR3 id, planets) from pscomppars."""
    hosts: dict[int, Host] = {}
    for row in tap_csv(net, PS_QUERY):
        tic = _tic(row["tic_id"])
        if not tic:
            continue
        h = hosts.get(tic)
        if h is None:
            h = hosts[tic] = Host(tic, row["hostname"], _tic(row["gaia_dr3_id"]) if row["gaia_dr3_id"] else None)
        h.planets.append(row["pl_name"])
    return hosts


def select_hosts(net: Net, tics: list[int] | None) -> tuple[list[Host], list[int]]:
    """(hosts to build, requested TICs the archive does not list as hosts)."""
    known = archive_hosts(net)
    if tics is None:
        return sorted(known.values(), key=lambda h: h.tic), []
    return [known[t] for t in tics if t in known], [t for t in tics if t not in known]

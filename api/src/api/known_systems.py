"""The "Known systems": stars pre-computed at deploy time so Analyze answers them instantly.

One list, here; web/ mirrors it. TICs checked against the TIC lookups (deploy/HOSTING.md, R4).
"""

from __future__ import annotations

import re

KNOWN_SYSTEMS: dict[str, int] = {
    "WASP-18": 100100827,
    "WASP-121": 22529346,
    "WASP-43": 36734222,
    "TOI-700": 150428135,
}


def name_key(name: str) -> str:
    """Case, spaces, dashes and a trailing planet letter don't matter: "wasp 18 b" -> "wasp18"."""
    key = re.sub(r"[\s\-_]+", "", name.strip().lower())
    return re.sub(r"(?<=\d)[b-i]$", "", key)


BY_KEY: dict[str, int] = {name_key(n): tic for n, tic in KNOWN_SYSTEMS.items()}
NAME_OF: dict[int, str] = {tic: n for n, tic in KNOWN_SYSTEMS.items()}

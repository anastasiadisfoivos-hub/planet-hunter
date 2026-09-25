"""The real PixelVetter (pixels/, vet_pixels) and KnownLists (pipeline/'s hunter.known)."""

from __future__ import annotations

from typing import Any

from api.finder import normalize_vet
from api.ports import KnownMatch


def _vet_pixels():
    # PIXELS ships the module as `pixels`; its package is also importable as `skypixels`.
    try:
        from pixels import vet_pixels
    except ImportError:
        from skypixels import vet_pixels
    return vet_pixels


class PixelsVetter:
    def __init__(self) -> None:
        self._vet_pixels = _vet_pixels()

    def vet(self, candidate: dict[str, Any]) -> dict[str, Any]:
        vet = self._vet_pixels(
            int(candidate["tic"]),
            float(candidate["period_d"]),
            float(candidate["t0_btjd"]),
            float(candidate["duration_h"]),
            sectors=[int(s) for s in candidate.get("sectors") or []] or None,
        )
        return normalize_vet(vet)


class HunterKnownLists:
    """Confirmed planets, TOIs, CTOIs and the TESS eclipsing-binary catalogue (Prsa+ 2022),
    matched on period within 1% or a clean alias (x2, x3, 1/2, 1/3)."""

    def match(self, tic: int, period_d: float) -> KnownMatch | None:
        from hunter.known import check

        result = check(int(tic), float(period_d), include_eb_catalogue=True)
        if result.status == "known":
            return KnownMatch(result.list_name or "known", result.name, result.alias)
        if result.status == "unchecked":
            raise ConnectionError("; ".join(result.errors) or "lists unreachable")
        return None

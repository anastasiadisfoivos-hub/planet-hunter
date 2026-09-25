"""The real PixelVetter (pixels/, vet_pixels) and KnownLists (pipeline/'s hunter.known)."""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path
from typing import Any

from api.finder import normalize_vet
from api.ports import KnownMatch


def _vet_pixels():
    # pixels/ is the `skypixels` package (the api's optional `finder` extra).
    try:
        from skypixels import vet_pixels
    except ImportError:
        from pixels import vet_pixels
    return vet_pixels


IMAGE_KEYS = ("out_of_transit", "difference", "markers")


def images_from(out_dir: Path, names: list[str]) -> dict[str, Any]:
    """PixelVet.images from the per-sector tic<id>_s<sector>_pixels.json files vet_pixels wrote:
    {out_of_transit, difference, markers} of the first sector, plus `sector` and every sector's
    full web JSON in `per_sector` (4-45 kB each)."""
    sectors = []
    for name in names:
        doc = json.loads((out_dir / name).read_text())
        m = re.search(r"_s(\d+)_pixels\.json$", name)
        sectors.append({"sector": int(m.group(1)) if m else None, **doc})
    if not sectors:
        return {}
    first = sectors[0]
    return {**{k: first.get(k) for k in IMAGE_KEYS}, "sector": first["sector"],
            "per_sector": sectors}  # fmt: skip


class PixelsVetter:
    def __init__(self, vet_pixels=None) -> None:
        self._vet_pixels = vet_pixels or _vet_pixels()

    def vet(self, candidate: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="ph-pixels-") as tmp:
            vet = self._vet_pixels(
                int(candidate["tic"]),
                float(candidate["period_d"]),
                float(candidate["t0_btjd"]),
                float(candidate["duration_h"]),
                sectors=[int(s) for s in candidate.get("sectors") or []] or None,
                out_dir=tmp,
            )
            doc = vet.to_dict() if hasattr(vet, "to_dict") else dict(vet)
            files = doc.pop("files", None) or {}
            if not doc.get("images"):
                doc["images"] = images_from(Path(tmp), list(files.get("json", [])))
        return normalize_vet(doc)


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

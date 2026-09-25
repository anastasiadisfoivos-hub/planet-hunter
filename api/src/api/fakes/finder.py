"""Fake PixelVetter and KnownLists for tests and PH_ADAPTERS=fake."""

from __future__ import annotations

from typing import Any

from api.ports import KnownMatch


class FakePixelVetter:
    """Every candidate is "on target", except `verdicts[tic]`; `fail` holds TICs that raise."""

    def __init__(self) -> None:
        self.verdicts: dict[int, str] = {}
        self.fail: set[int] = set()
        self.calls: list[int] = []

    def vet(self, candidate: dict[str, Any]) -> dict[str, Any]:
        tic = int(candidate["tic"])
        self.calls.append(tic)
        if tic in self.fail:
            raise RuntimeError(f"no pixel data for TIC {tic}")
        verdict = self.verdicts.get(tic, "on target")
        on_target = verdict == "on target"
        return {
            "verdict": verdict,
            "reason": "the dip is centred on the target star" if on_target
            else "the dip is centred between the target and a neighbour",
            "on_target_probability": 0.97 if on_target else 0.2,
            "centroid_offset_arcsec": 1.2 if on_target else 18.5,
            "offset_sigma": 0.6 if on_target else 4.1,
            "suspect_neighbours": [] if on_target else [
                {"tic": tic + 1, "separation_arcsec": 21.0, "tmag": 12.3}
            ],
            "per_sector": [{"sector": s, "offset_arcsec": 1.1}
                           for s in candidate.get("sectors", [])],
            "images": {"out_of_transit": [[1.0, 2.0], [3.0, 4.0]],
                       "difference": [[0.0, 0.1], [0.0, 0.0]],
                       "markers": [{"kind": "target", "x": 0.5, "y": 0.5}]},
        }  # fmt: skip


class FakeKnownLists:
    """`matches[tic]` is on a list; `down` makes every call raise."""

    def __init__(self) -> None:
        self.matches: dict[int, KnownMatch] = {}
        self.down = False
        self.calls: list[int] = []

    def match(self, tic: int, period_d: float) -> KnownMatch | None:
        self.calls.append(tic)
        if self.down:
            raise ConnectionError("lists unreachable")
        return self.matches.get(tic)

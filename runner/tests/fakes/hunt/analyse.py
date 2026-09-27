from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Result:
    tic: int
    sectors: list
    signals: list
    candidates: list
    star: dict = field(default_factory=dict)

    def summary(self) -> dict:
        return {"tic": self.tic, "list": "A", "star": self.star, "sectors": self.sectors, "signals": self.signals,
                "dips": [], "masked_known": [], "events": [], "n_candidates": len(self.candidates), "error": None,
                "timings_s": {}}


def analyse(star, lc, catalogue, list_kind="A", max_signals=3, check_known=True, deep_search=True,
            dip_search=True, tls_budget_s=None):
    tic = star.tic
    if tic % 11 == 0:
        raise RuntimeError("simulated MAST failure")
    done = os.environ.get("FAKE_HUNT_DONE_LOG")
    sigs, cands = [], []
    if tic % 5 == 0:
        sigs.append({"n": 1, "kind": "periodic", "period_d": 3.5, "t0_btjd": 1501.2, "duration_h": 2.0,
                     "depth_ppm": 900.0, "snr": 14.0, "sde": 12.0, "n_transits": 5, "failed_stage": None,
                     "failed_checks": [], "failed_reasons": {}, "known_names": [], "score": 0.4})
        cands.append({"id": f"hunt:{tic}:1", "tic": tic, "kind": "periodic", "status": "candidate",
                      "period_d": 3.5, "t0_btjd": 1501.2, "duration_h": 2.0, "depth_ppm": 900.0, "snr": 14.0,
                      "sde": 12.0, "n_transits": 5, "sectors": lc.sectors, "radius_rjup": [0.1, 0.12],
                      "radius_low": 0.1, "radius_high": 0.12, "radius_rjup_best": 0.11, "radius_rearth_best": 1.2,
                      "checks": [], "score": 0.4, "score_parts": {}, "single_sector_only": False,
                      "search_list": "new-star search", "known_lists": {"status": "not_on_lists"},
                      "deep": deep_search, "created_at": "2026-09-27T00:00:00+00:00"})
    if tic % 10 == 0:
        sigs.append({"n": 2, "kind": "periodic", "period_d": 11.0, "t0_btjd": 1503.0, "duration_h": 3.0,
                     "depth_ppm": 400.0, "snr": 8.0, "sde": 6.0, "n_transits": 2, "failed_stage": "sde",
                     "failed_checks": [], "known_names": [], "score": 0.1})
    sigs.append({"n": len(sigs) + 1, "kind": "periodic", "period_d": 1.1, "t0_btjd": 1500.3, "duration_h": 1.0,
                 "depth_ppm": 150.0, "snr": 5.2, "sde": 7.0, "n_transits": 15, "failed_stage": "snr",
                 "failed_checks": [], "known_names": [], "score": 0.0})
    if done:
        with open(done, "a") as fh:
            fh.write(f"{tic} {'deep' if deep_search else 'fast'}\n")
    return Result(tic, lc.sectors, sigs, cands, star.to_row())

"""Fake TESS hunter: deterministic signals per TIC, controllable from tests."""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from api.contract import CatchType, Cutouts, Discovery, LightCurve, Link

BTJD_EPOCH = datetime(2014, 12, 8, 12, tzinfo=UTC)  # BTJD 0 = JD 2457000.0

STEPS = (
    "downloading TESS light curve",
    "cleaning and detrending",
    "searching for repeating dips",
    "checking for flares",
    "vetting candidates",
)


def btjd_to_datetime(btjd: float) -> datetime:
    return BTJD_EPOCH + timedelta(days=btjd)


class FakeStarHunter:
    """`markers[tic]` sets the data marker; `gate` (if set) blocks every hunt until released."""

    def __init__(self, step_delay_s: float = 0.0, seed: int = 0):
        self.step_delay_s = step_delay_s
        self.seed = seed
        self.markers: dict[int, str | None] = {}
        self.gate: threading.Event | None = None
        self.fail_for: set[int] = set()
        self.hunt_calls: list[int] = []
        self._lock = threading.Lock()
        self.running = 0
        self.max_running_seen = 0

    def latest_data_marker(self, tic_id: int) -> str | None:
        if tic_id in self.markers:
            return self.markers[tic_id]
        return f"sector-{random.Random(f'{self.seed}:m:{tic_id}').randint(1, 80)}"

    def hunt(self, tic_id: int, progress: Callable[[str], None]) -> list[Discovery]:
        with self._lock:
            self.hunt_calls.append(tic_id)
            self.running += 1
            self.max_running_seen = max(self.max_running_seen, self.running)
        try:
            if self.gate is not None:
                self.gate.wait(timeout=30)
            for step in STEPS:
                progress(step)
                if self.step_delay_s:
                    time.sleep(self.step_delay_s)
            if tic_id in self.fail_for:
                raise RuntimeError(f"no usable light curve for TIC {tic_id}")
            return self._results(tic_id)
        finally:
            with self._lock:
                self.running -= 1

    def _results(self, tic_id: int) -> list[Discovery]:
        rng = random.Random(f"{self.seed}:star:{tic_id}")
        marker = self.latest_data_marker(tic_id) or "none"
        jitter = random.Random(f"{self.seed}:jitter:{tic_id}:{marker}")
        ra, dec = rng.uniform(0, 360), math.degrees(math.asin(rng.uniform(-1, 1)))
        out: list[Discovery] = []
        for n in range(1, rng.randint(1, 2) + 1):
            period = round(rng.uniform(0.8, 20.0) * (1 + jitter.uniform(-0.003, 0.003)), 5)
            kind = CatchType.planet_candidate if rng.random() < 0.6 else CatchType.eclipsing_binary
            conf = round(rng.uniform(0.3, 0.9), 2)
            t0 = round(rng.uniform(1400, 3000), 4)
            out.append(
                self._disc(
                    tic_id,
                    f"tess:{tic_id}:sig:{n}",
                    kind,
                    conf,
                    ra,
                    dec,
                    t0,
                    {"fake": True, "period_days": period, "t0_btjd": t0, "marker": marker},
                    f"Best guess: {kind.value.replace('_', ' ')} (confidence {conf:.2f}). "
                    f"The star dims by a small amount every {period:.3f} days. "
                    "It needs follow-up before anyone can say what it is.",
                )
            )
        if rng.random() < 0.5:
            peak = round(rng.uniform(1400, 3000), 3)
            out.append(
                self._disc(
                    tic_id,
                    f"tess:{tic_id}:flare:{peak:.2f}",
                    CatchType.flare,
                    0.8,
                    ra,
                    dec,
                    peak,
                    {"fake": True, "peak_btjd": peak, "marker": marker},
                    "Best guess: flare (confidence 0.80). The star brightened sharply "
                    "for a few minutes and then faded back.",
                )
            )
        return out

    @staticmethod
    def _disc(tic, did, kind, conf, ra, dec, btjd, raw, text) -> Discovery:
        times = [btjd + i * 0.02 for i in range(200)]
        flux = [1.0 - (0.01 if 90 <= i < 100 else 0.0) for i in range(200)]
        return Discovery(
            id=did,
            type=kind,
            confidence=conf,
            source="tess",
            origin="fake-tess-hunt",
            ra_deg=round(ra, 6),
            dec_deg=round(dec, 6),
            detected_at=btjd_to_datetime(btjd),
            name_if_known=f"TIC {tic}",
            known_status="unchecked",
            cutouts=Cutouts(),
            light_curve=LightCurve(time_btjd=times, flux=flux),
            explanation=text,
            links=[
                Link(
                    label="ExoFOP page for this star",
                    url=f"https://exofop.ipac.caltech.edu/tess/target.php?id={tic}",
                )
            ],
            raw=raw,
        )

"""Fake TESS analyzer: deterministic results per TIC and data marker, controllable from tests."""

from __future__ import annotations

import math
import random
import threading
import time
from collections.abc import Callable

from api.analysis import describe
from api.known_systems import BY_KEY, NAME_OF, name_key
from api.models import Analysis, Check, Flare, FoldedCurve, Link, Sector, Signal, StarInfo

STEPS = (
    "looking up the star",
    "downloading TESS light curves",
    "searching for repeating dips",
    "checking for flares",
)


class FakeAnalyzer:
    """`markers[tic]` sets the data marker (None: no TESS data); `marker_down` makes the marker
    check raise; `gate` (if set) blocks every analysis until released."""

    def __init__(self, step_delay_s: float = 0.0, seed: int = 0):
        self.step_delay_s = step_delay_s
        self.seed = seed
        self.markers: dict[int, str | None] = {}
        self.marker_down = False
        self.gate: threading.Event | None = None
        self.fail_for: set[int] = set()
        self.extra_text = ""  # appended to explanations (honesty tests)
        self.hunt_calls: list[int] = []
        self.marker_calls: list[int] = []
        self.resolve_calls: list[str] = []
        self._lock = threading.Lock()
        self.running = 0
        self.max_running_seen = 0

    def resolve(self, name: str) -> StarInfo:
        self.resolve_calls.append(name)
        key = name_key(name)
        if key in BY_KEY:
            return StarInfo(tic_id=BY_KEY[key], name=name)
        if key.startswith("fakestar") and key[8:].isdigit():
            return StarInfo(tic_id=int(key[8:]), name=name)
        raise LookupError(f"could not resolve {name!r} to a TIC star")

    def latest_data_marker(self, tic_id: int) -> str | None:
        with self._lock:
            self.marker_calls.append(tic_id)
        if self.marker_down:
            raise ConnectionError("MAST did not answer")
        return self._marker(tic_id)

    def _marker(self, tic_id: int) -> str | None:
        if tic_id in self.markers:
            return self.markers[tic_id]
        return f"sector-{random.Random(f'{self.seed}:m:{tic_id}').randint(1, 80)}"

    def analyze(self, tic_id: int, progress: Callable[[str], None]) -> Analysis:
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
                raise LookupError(f"no usable light curve for TIC {tic_id}")
            marker = self._marker(tic_id) or "none"
            return self._result(tic_id, marker)
        finally:
            with self._lock:
                self.running -= 1

    def _result(self, tic_id: int, marker: str) -> Analysis:
        rng = random.Random(f"{self.seed}:star:{tic_id}")
        jitter = random.Random(f"{self.seed}:jitter:{tic_id}:{marker}")
        sector = int(marker.split("-")[-1]) if marker.startswith("sector-") else 1
        links = [
            Link(
                label="ExoFOP-TESS target page",
                url=f"https://exofop.ipac.caltech.edu/tess/target.php?id={tic_id}",
            )
        ]
        signals = []
        for n in range(1, rng.randint(1, 2) + 1):
            period = round(rng.uniform(0.8, 20.0) * (1 + jitter.uniform(-0.003, 0.003)), 5)
            kind = "planet_candidate" if rng.random() < 0.6 else "eclipsing_binary"
            depth = rng.uniform(0.001, 0.02)
            phase = [round(-0.5 + (i + 0.5) / 1000, 5) for i in range(1000)]
            flux = [round(1 - depth if abs(p) < 0.02 else 1.0, 6) for p in phase]
            signals.append(
                Signal(
                    id=f"tess:{tic_id}:sig:{n}",
                    type=kind,
                    confidence=round(rng.uniform(0.3, 0.9), 2),
                    period_days=period,
                    t0_btjd=round(rng.uniform(1400, 3000), 4),
                    duration_hours=round(rng.uniform(1, 5), 2),
                    depth_ppm=round(depth * 1e6, 1),
                    snr=round(rng.uniform(8, 80), 1),
                    n_transits=rng.randint(3, 30),
                    known_status="unchecked",
                    explanation=(
                        f"Best guess: {kind.replace('_', ' ')}. The star dims by a small amount "
                        f"every {period:.3f} days.{self.extra_text}"
                    ),
                    checks=[Check(name="snr", passed=True, reason="The dips stand out clearly.")],
                    links=links,
                    folded=FoldedCurve(phase=phase, flux=flux),
                )
            )
        flares = []
        if rng.random() < 0.5:
            peak = round(rng.uniform(1400, 3000), 3)
            flares.append(
                Flare(
                    id=f"tess:{tic_id}:flare:{peak:.2f}",
                    peak_btjd=peak,
                    peak_at="2024-01-01T00:00:00Z",
                    amplitude=0.01,
                    confidence=0.8,
                    explanation="Best guess: a stellar flare. The star brightened sharply.",
                )
            )
        ra, dec = rng.uniform(0, 360), math.degrees(math.asin(rng.uniform(-1, 1)))
        sectors = [Sector(sector=sector, author="SPOC", exptime=120.0)]
        star = StarInfo(
            tic_id=tic_id, name=NAME_OF.get(tic_id), ra_deg=round(ra, 5), dec_deg=round(dec, 5)
        )
        return Analysis(
            star=star,
            sectors=sectors,
            signals=signals,
            flares=flares,
            flares_found=len(flares),
            signals_examined=len(signals),
            summary=describe(star, sectors, signals, len(flares)),
            links=links,
        )

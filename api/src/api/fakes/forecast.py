"""Fake forecaster: plausible, deterministic numbers in the contract's Forecast shape."""

from __future__ import annotations

import random
from datetime import datetime, timedelta

from api.contract import (
    CatchType,
    ExpectedCount,
    Forecast,
    KnownSolarSystemObject,
    Sphere,
    Visit,
    Window,
)
from api.timeutil import utcnow

_RATES = {  # expected per square degree per night
    CatchType.asteroid: 0.9,
    CatchType.variable_star: 0.5,
    CatchType.supernova: 0.08,
    CatchType.active_galaxy: 0.05,
    CatchType.near_earth_object: 0.01,
    CatchType.comet: 0.002,
}


class FakeForecaster:
    def __init__(self, seed: int = 0):
        self.seed = seed

    def forecast(self, sphere: Sphere, start: datetime, end: datetime) -> Forecast:
        rng = random.Random(
            f"{self.seed}:{sphere.ra_deg:.2f}:{sphere.dec_deg:.2f}:{sphere.radius_deg:.2f}:"
            f"{start.date()}"
        )
        nights = max(1, round((end - start).total_seconds() / 86_400))
        area = 3.14159 * sphere.radius_deg**2
        # Rubin sees the southern sky; the far north is out of reach.
        reach = 0.0 if sphere.dec_deg > 30 else 0.85 if sphere.dec_deg < 0 else 0.5
        visits = []
        t = start
        while t < end and len(visits) < 200:
            if rng.random() < reach * 0.4:
                visits.append(
                    Visit(time=t + timedelta(hours=rng.uniform(0, 8)), band=rng.choice("ugrizy"))
                )
            t += timedelta(days=1)
        visits = [v for v in visits if v.time < end]
        prob = 1 - (1 - reach * 0.4) ** nights if reach else 0.0
        return Forecast(
            sphere=sphere,
            window=Window(start=start, end=end),
            rubin_visit_probability=round(min(1.0, prob), 3),
            visits=visits,
            expected=[
                ExpectedCount(type=t, mean_count=round(r * area * nights * reach, 3))
                for t, r in _RATES.items()
            ],
            known_solar_system_objects=[
                KnownSolarSystemObject(
                    name=f"FAKE ({2000 + i}) object",
                    type=CatchType.asteroid,
                    ra_deg=(sphere.ra_deg + rng.uniform(-1, 1) * sphere.radius_deg * 0.7) % 360,
                    dec_deg=max(
                        -90, min(90, sphere.dec_deg + rng.uniform(-1, 1) * sphere.radius_deg * 0.7)
                    ),
                )
                for i in range(rng.randint(0, 3))
            ],
            generated_at=utcnow(),
            inputs_used=["fake-forecaster"],
        )

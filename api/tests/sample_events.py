"""Hand-made Events (SHARED EVENT CONTRACT) covering every filter dimension."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta
from typing import Any

NOW = datetime(2026, 9, 25, 12, tzinfo=UTC)


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def image(url: str, kind: str = "sky_context") -> dict[str, Any]:
    return {
        "url": url,
        "thumb_url": url + "?thumb",
        "kind": kind,
        "caption": "Archival picture of this patch of sky.",
        "credit": "CDS hips2fits",
        "license": "CC BY 4.0",
        "width": 800,
        "height": 800,
    }


def event(
    eid: str,
    etype: str,
    *,
    hours_ago: float,
    source: str | None = None,
    sky: tuple[float, float] | None = None,
    frame: str = "sky",
    confidence: float = 0.9,
    images: list[dict] | None = None,
    raw: dict | None = None,
    summary: str = "A change in brightness was reported.",
) -> dict[str, Any]:
    source = source or eid.split(":", 1)[0]
    if frame == "sky":
        ra, dec = sky or (10.0, 10.0)
        loc: dict[str, Any] = {"frame": "sky", "ra_deg": ra, "dec_deg": dec, "error_deg": 0.001}
    elif frame == "sun":
        loc = {"frame": "sun"}
    else:
        loc = {"frame": "earth", "lat_deg": 10.0, "lon_deg": 20.0, "alt_km": 30.0}
    t = NOW - timedelta(hours=hours_ago)
    return {
        "id": eid,
        "type": etype,
        "title": f"{etype.replace('_', ' ')} {eid}",
        "summary": summary,
        "source": source,
        "source_url": f"https://example.org/{eid}",
        "observed_at": iso(t),
        "reported_at": iso(t + timedelta(hours=1)),
        "location": loc,
        "confidence": confidence,
        "confidence_basis": "official_report",
        "brightness_mag": None,
        "images": images or [],
        "raw": raw or {},
    }


def sample() -> list[dict[str, Any]]:
    return copy.deepcopy(
        [
            event("tns:2026abc", "supernova", hours_ago=2, sky=(150.0, -20.0),
                  images=[image("https://img.example/sn.jpg")],
                  raw={"sources": [{"source": "tns", "url": "u"}, {"source": "ztf", "url": "u"}]}),
            event("ztf:ZTF26aaa", "tidal_disruption_event", hours_ago=5, sky=(151.0, -21.0),
                  confidence=0.4),
            event("rubin:1001", "supernova", hours_ago=30, sky=(359.8, 0.5), confidence=0.6,
                  raw={"from_latest_observed_window": True}),
            event("mpc:LS123", "near_earth_object", hours_ago=10, sky=(0.3, 0.2), confidence=0.7),
            event("jpl:C2026A1", "comet", hours_ago=24 * 20, sky=(200.0, 60.0)),
            event("donki:FLR-1", "solar_flare", hours_ago=3, frame="sun",
                  images=[image("https://sdo.example/131.jpg", "solar")]),
            event("donki:GST-1", "geomagnetic_storm", hours_ago=8, frame="earth"),
            event("cneos:fb1", "fireball", hours_ago=48, frame="earth", confidence=1.0),
            event("gcn:GRB260925A", "gamma_ray_burst", hours_ago=1, sky=(0.0, -89.5)),
            event("gracedb:S260920x", "gravitational_wave", hours_ago=24 * 5, sky=(80.0, 30.0),
                  confidence=0.95),
            event("icecube:IC260921A", "neutrino", hours_ago=24 * 4, sky=(80.5, 30.5),
                  confidence=0.3),
            event("ztf:ZTF26bbb", "unknown", hours_ago=12, sky=(150.5, -20.5), confidence=0.2),
        ]
    )  # fmt: skip

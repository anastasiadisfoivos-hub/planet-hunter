"""NASA/JPL CNEOS fireballs: bright meteors seen by US government sensors. Earth frame.

API: https://ssd-api.jpl.nasa.gov/doc/fireball.html (no key). Reports appear days to weeks after
the event; the API gives no report time, so reported_at = observed_at (raw.reported_at_known=False).
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..models import Event
from ..util import as_utc, iso, make_event, num
from ._http import FRESH, client

NAME = "cneos"
LIVE_WITHIN = timedelta(days=60)  # fireballs are sporadic and posted with delay
API = "https://ssd-api.jpl.nasa.gov/fireball.api"
PAGE = "https://cneos.jpl.nasa.gov/fireballs/"


def fetch(since: datetime, until: datetime) -> list[Event]:
    params = {
        "date-min": iso(since)[:19],
        "date-max": iso(until)[:19],
        "req-loc": "true",
    }
    return _rows(client().get_json(API, params=params, ttl=FRESH))


def last_event_at(now: datetime) -> datetime | None:
    events = _rows(client().get_json(API, params={"limit": 1}, ttl=FRESH))
    return as_utc(events[0]["observed_at"]) if events else None


def _rows(doc: dict) -> list[Event]:
    fields = doc.get("fields", [])
    return [e for row in doc.get("data", []) if (e := to_event(dict(zip(fields, row, strict=False))))]


def to_event(r: dict) -> Event | None:
    lat, lon = num(r.get("lat")), num(r.get("lon"))
    if lat is None or lon is None:
        return None
    lat = -lat if r.get("lat-dir") == "S" else lat
    lon = -lon if r.get("lon-dir") == "W" else lon
    alt, energy, impact, vel = num(r.get("alt")), num(r.get("energy")), num(r.get("impact-e")), num(r.get("vel"))
    when = as_utc(r["date"])
    where = f"{abs(lat):.1f}°{'N' if lat >= 0 else 'S'} {abs(lon):.1f}°{'E' if lon >= 0 else 'W'}"
    height = f", about {alt:.0f} km up" if alt is not None else ""
    power = f" It gave off about {energy:g}×10¹⁰ J of light" if energy is not None else ""
    power += f" (estimated impact energy {impact:g} kt of TNT)." if impact is not None else ("." if power else "")
    return make_event(
        source=NAME,
        source_id=iso(when).rstrip("Z"),
        type="fireball",
        title=f"Fireball at {where}",
        summary=f"US government sensors recorded a bright fireball (a meteor) at {where}{height}.{power}",
        source_url=PAGE,
        observed_at=when,
        reported_at=when,
        location={"frame": "earth", "lat_deg": lat, "lon_deg": lon, "alt_km": alt},
        confidence=1.0,
        confidence_basis="official_report",
        raw={
            "radiated_energy_1e10_J": energy,
            "impact_energy_kt": impact,
            "velocity_km_s": vel,
            "reported_at_known": False,
        },
    )

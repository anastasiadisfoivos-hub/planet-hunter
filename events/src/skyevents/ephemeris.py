"""3D positions of Solar-System objects at the time they were observed.

- Objects with a designation (JPL's comets): JPL Horizons vectors
  (https://ssd-api.jpl.nasa.gov/doc/horizons.html), EPHEM_TYPE=VECTORS, centre the Sun, ecliptic
  J2000, geometric. One request per object, cached for good (a past epoch never changes).
- Asteroids a survey saw once (ZTF's "asteroid" detections): IMCCE's SkyBoT cone search
  (https://ssp.imcce.fr/webservices/skybot/) names the known asteroid at that place and time, seen
  from the survey's observatory (MPC code); the nearest within IDENT_RADIUS_ARCSEC wins, and
  Horizons gives its vectors as above. (JPL's sb_ident does the same but took over 200 s per
  call on 2026-09-26; SkyBoT answers in a few seconds.)
- Objects still on the MPC confirmation pages have only a temporary designation, which Horizons
  does not know. JPL Scout (https://ssd-api.jpl.nasa.gov/doc/scout.html) publishes N_ORBITS
  sampled orbits that fit their observations; each is moved to the epoch with two-body Kepler
  motion (the arcs are days long, so planetary perturbations are far below the orbit's own
  uncertainty) and the component-wise median is the position. The spread of Earth distances
  over the samples goes to raw.

Earth's heliocentric position comes from ERFA's epv00 (a few km accuracy), rotated from ICRS to
ecliptic J2000 with the obliquity Horizons uses (84381.448"), so earth_distance_au is geometric.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime

import erfa
import numpy as np
from astropy.time import Time

from .adapters._http import DAY, FOREVER, UpstreamError, client
from .models import Ephemeris
from .util import as_utc, iso

HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
SCOUT = "https://ssd-api.jpl.nasa.gov/scout.api"
SKYBOT = "https://ssp.imcce.fr/webservices/skybot/api/conesearch.php"
IDENT_RADIUS_ARCSEC = 5.0
OBSERVATORY = {"ztf": "I41", "rubin": "X05"}  # MPC codes: Palomar (ZTF), Rubin; else Earth's centre
N_ORBITS = 50
GAUSS_K = 0.01720209895  # rad/day, Gaussian gravitational constant (heliocentric, au)
OBLIQUITY_J2000 = math.radians(84381.448 / 3600)


def _rot_ecliptic(xyz: np.ndarray) -> np.ndarray:
    """ICRS/equatorial -> ecliptic J2000."""
    c, s = math.cos(OBLIQUITY_J2000), math.sin(OBLIQUITY_J2000)
    x, y, z = xyz
    return np.array([x, c * y + s * z, -s * y + c * z])


def earth_helio_ecliptic(t: datetime) -> np.ndarray:
    tdb = Time(as_utc(t)).tdb
    pvh, _ = erfa.epv00(tdb.jd1, tdb.jd2)
    return _rot_ecliptic(np.asarray(pvh[0], dtype=float))


def ephemeris_from_xyz(xyz: np.ndarray | list[float], t: datetime) -> Ephemeris:
    v = np.asarray(xyz, dtype=float)
    return {
        "helio_xyz_au": [round(float(c), 8) for c in v],
        "earth_distance_au": round(float(np.linalg.norm(v - earth_helio_ecliptic(t))), 8),
        "sun_distance_au": round(float(np.linalg.norm(v)), 8),
        "epoch": iso(t),
    }


# ------------------------------------------------------------------ Horizons


def horizons_params(command: str, t: datetime, center: str = "500@10") -> dict:
    return {
        "format": "json",
        "COMMAND": f"'{command}'",
        "EPHEM_TYPE": "VECTORS",
        "CENTER": f"'{center}'",
        "REF_PLANE": "ECLIPTIC",
        "REF_SYSTEM": "J2000",
        "OUT_UNITS": "AU-D",
        "VEC_TABLE": "1",
        "VEC_CORR": "NONE",
        "TLIST": f"'{Time(as_utc(t)).utc.jd:.6f}'",
        "TIME_TYPE": "UT",
        "OBJ_DATA": "NO",
        "CSV_FORMAT": "YES",
    }


def horizons_xyz(command: str, t: datetime, center: str = "500@10") -> np.ndarray | None:
    doc = client().get_json(HORIZONS, params=horizons_params(command, t, center), ttl=FOREVER)
    if "result" not in doc:
        raise UpstreamError(f"Horizons: {doc.get('message') or doc.get('error')}")
    return parse_vectors(doc["result"])


def parse_vectors(result: str) -> np.ndarray | None:
    """First row of a CSV vector table: 'JDUT, Calendar, X, Y, Z,'."""
    m = re.search(r"\$\$SOE\s*\n(.*?)\n", result)
    if not m:
        return None
    cells = [c.strip() for c in m[1].split(",")]
    return np.array([float(c) for c in cells[2:5]])


def designated(pdes: str, t: datetime) -> tuple[Ephemeris, str] | None:
    xyz = horizons_xyz(f"DES={pdes};CAP;NOFRAG", t)
    if xyz is None:
        return None
    return ephemeris_from_xyz(xyz, t), f"JPL Horizons vectors for {pdes}"


# ------------------------------------------------------------------ SkyBoT (one-off detections)


def identify(ra: float, dec: float, t: datetime, mpc_code: str) -> tuple[str, float, str | None] | None:
    """(name as "180274 (2003 WC63)" or "(2026 AB12)", offset in arcsec, SkyBoT class) of the
    nearest known asteroid within IDENT_RADIUS_ARCSEC of (ra, dec) at t, or None."""
    params = {
        "-ep": f"{Time(as_utc(t)).utc.jd:.6f}", "-ra": f"{ra:.7f}", "-dec": f"{dec:.7f}",
        "-rs": f"{IDENT_RADIUS_ARCSEC:g}", "-mime": "json", "-output": "basic", "-observer": mpc_code,
        "-objFilter": "100", "-refsys": "EQJ2000", "-from": "planet-hunter",
    }
    text = client().request_text("GET", SKYBOT, params=params, ttl=FOREVER).strip()
    if _skybot_failed(text):
        # SkyBoT sometimes crashes server-side and says so with HTTP 200, which the client has
        # cached; ask once more past the cache.
        text = client().request_text("GET", SKYBOT, params=params, ttl=0).strip()
    if _skybot_failed(text):
        raise UpstreamError(f"SkyBoT: {text[:200]}")
    if not text.startswith("["):  # SkyBoT answers plain text when nothing is there
        return None
    rows = [r for r in json.loads(text) if r.get("d (arcsec)") is not None]
    if not rows:
        return None
    best = min(rows, key=lambda r: float(r["d (arcsec)"]))
    off = float(best["d (arcsec)"])
    if off > IDENT_RADIUS_ARCSEC:
        return None
    num_, name = best.get("Num"), str(best.get("Name") or "").strip()
    label = f"{num_} ({name})" if num_ not in (None, "", "-") else f"({name})"
    return label, off, best.get("Class")


def _skybot_failed(text: str) -> bool:
    return not text.startswith("[") and '"flag":-1' in text.replace(" ", "")


def horizons_command(name: str) -> str:
    """Asteroid label -> Horizons small-body command: "180274 (2003 WC63)" -> "180274;",
    "(2026 AB12)" or "2026 AB12" -> "DES=2026 AB12;"."""
    if m := re.match(r"^(\d+)\b", name):
        return f"{m[1]};"
    return f"DES={name.strip('() ')};"


def one_off(ra: float, dec: float, t: datetime, source: str) -> tuple[Ephemeris, str, dict] | None:
    got = identify(ra, dec, t, OBSERVATORY.get(source, "500"))
    if not got:
        return None
    name, off, cls = got
    xyz = horizons_xyz(horizons_command(name), t)
    if xyz is None:
        return None
    return ephemeris_from_xyz(xyz, t), f"JPL Horizons vectors for {name}", {
        "identified_as": name, "identified_offset_arcsec": round(off, 2), "identified_by": "IMCCE SkyBoT",
        "asteroid_class": cls}


# ------------------------------------------------------------------ Scout (unconfirmed objects)


def scout_orbits(tdes: str) -> list[dict]:
    doc = client().get_json(SCOUT, params={"tdes": tdes, "orbits": 1, "n-orbits": N_ORBITS}, ttl=DAY)
    orbits = (doc or {}).get("orbits") or {}
    fields = orbits.get("fields") or []
    return [dict(zip(fields, row, strict=False)) for row in orbits.get("data") or []]


def kepler_xyz(q: float, e: float, tp_jd: float, om: float, w: float, inc: float, jd: float) -> np.ndarray:
    """Heliocentric ecliptic position (au) from perihelion elements, two-body motion.
    Angles in degrees; tp and jd on the same (TDB) scale."""
    if abs(e - 1.0) < 1e-9:
        e = 1.0 - 1e-9
    dt = jd - tp_jd
    if e < 1.0:
        a = q / (1.0 - e)
        m = GAUSS_K * dt / a**1.5
        m = math.remainder(m, 2 * math.pi)
        ea = m if e < 0.8 else math.pi * (1 if m >= 0 else -1)
        for _ in range(100):
            d = (ea - e * math.sin(ea) - m) / (1 - e * math.cos(ea))
            ea -= d
            if abs(d) < 1e-14:
                break
        x_p, y_p = a * (math.cos(ea) - e), a * math.sqrt(1 - e * e) * math.sin(ea)
    else:
        a = q / (e - 1.0)
        m = GAUSS_K * dt / a**1.5
        h = math.asinh(m / e)
        for _ in range(200):
            d = (e * math.sinh(h) - h - m) / (e * math.cosh(h) - 1)
            h -= d
            if abs(d) < 1e-14:
                break
        x_p, y_p = a * (e - math.cosh(h)), a * math.sqrt(e * e - 1) * math.sinh(h)
    o, ww, i = map(math.radians, (om, w, inc))
    co, so, cw, sw, ci, si = math.cos(o), math.sin(o), math.cos(ww), math.sin(ww), math.cos(i), math.sin(i)
    x = (co * cw - so * sw * ci) * x_p + (-co * sw - so * cw * ci) * y_p
    y = (so * cw + co * sw * ci) * x_p + (-so * sw + co * cw * ci) * y_p
    z = (sw * si) * x_p + (cw * si) * y_p
    return np.array([x, y, z])


def unconfirmed(tdes: str, t: datetime) -> tuple[Ephemeris, str, dict] | None:
    orbits = scout_orbits(tdes)
    if not orbits:
        return None
    jd = Time(as_utc(t)).tdb.jd
    pts = np.array([
        kepler_xyz(float(o["qr"]), float(o["ec"]), float(o["tp"]), float(o["om"]), float(o["w"]), float(o["inc"]), jd)
        for o in orbits
    ])
    earth = earth_helio_ecliptic(t)
    dists = np.linalg.norm(pts - earth, axis=1)
    eph = ephemeris_from_xyz(np.median(pts, axis=0), t)
    spread = {
        "orbits": len(orbits),
        "earth_distance_au_p16_p84": [round(float(np.percentile(dists, 16)), 6), round(float(np.percentile(dists, 84)), 6)],
    }
    return eph, f"JPL Scout, median of {len(orbits)} sampled orbits for {tdes}", spread

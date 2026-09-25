"""Sky context: a real colour survey image of the exact spot, cut by CDS hips2fits.

Survey: the sharpest colour survey whose footprint covers the position (asked of the CDS
MocServer), falling back to all-sky DSS2. Field of view: set by the event type (host-galaxy
scale for supernovae, wider for moving objects), widened to show the position error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlencode

from . import credits
from .models import Event, Image
from .net import FetchError, get_net

log = logging.getLogger(__name__)

HIPS2FITS = "https://alasky.cds.unistra.fr/hips-image-services/hips2fits"
MOCSERVER = "https://alasky.cds.unistra.fr/MocServer/query"
FULL_PX = 800
THUMB_PX = 256
MAX_FOV_DEG = 60.0
NARROW_FOV_DEG = 0.5  # above this, only all-sky DSS2 (deep surveys are slow and patchy that wide)


@dataclass(frozen=True)
class Survey:
    hips_id: str
    name: str
    epoch: str
    credit: credits.Credit


LEGACY = Survey("CDS/P/DESI-Legacy-Surveys/DR10/color", "DESI Legacy Surveys DR10", "between 2013 and 2021",
                credits.LEGACY)
PANSTARRS = Survey("CDS/P/PanSTARRS/DR1/color-z-zg-g", "Pan-STARRS1", "between 2010 and 2014",
                   credits.PANSTARRS)
DSS2 = Survey("CDS/P/DSS2/color", "DSS2", "on photographic plates in the 1980s and 1990s", credits.DSS2)
PREFERENCE = [LEGACY, PANSTARRS, DSS2]

ARCMIN = 1 / 60
# Field of view (degrees) per event type, before widening for the position error.
FOV_DEG: dict[str, float] = {
    "supernova": 2.5 * ARCMIN,         # the host galaxy and its surroundings
    "kilonova": 2.5 * ARCMIN,
    "tidal_disruption_event": 1.5 * ARCMIN,  # a galaxy nucleus
    "active_galaxy_flare": 1.5 * ARCMIN,
    "nova": 3 * ARCMIN,
    "variable_star": 1.5 * ARCMIN,
    "stellar_flare": 1.5 * ARCMIN,
    "microlensing": 1.5 * ARCMIN,
    "unknown": 2 * ARCMIN,
    "asteroid": 20 * ARCMIN,           # moving objects: the star field it is crossing
    "near_earth_object": 30 * ARCMIN,
    "comet": 30 * ARCMIN,
    "interstellar_object": 20 * ARCMIN,
    "gamma_ray_burst": 3 * ARCMIN,
    "neutrino": 1.0,
    "gravitational_wave": 10.0,
}
DEFAULT_FOV_DEG = 2 * ARCMIN
MOVING = {"asteroid", "near_earth_object", "comet", "interstellar_object"}
STARS = {"variable_star", "stellar_flare", "microlensing"}
MESSENGERS = {"gamma_ray_burst", "neutrino", "gravitational_wave"}

NOUN = {
    "supernova": "supernova", "kilonova": "kilonova", "tidal_disruption_event": "tidal disruption event",
    "active_galaxy_flare": "flaring galaxy nucleus", "nova": "nova", "variable_star": "variable star",
    "stellar_flare": "flaring star", "microlensing": "microlensing event", "asteroid": "asteroid",
    "near_earth_object": "near-Earth object", "comet": "comet", "interstellar_object": "interstellar object",
    "gamma_ray_burst": "gamma-ray burst", "neutrino": "neutrino", "gravitational_wave": "gravitational-wave source",
}


def field_of_view(event_type: str, error_deg: float | None) -> float:
    fov = FOV_DEG.get(event_type, DEFAULT_FOV_DEG)
    if error_deg and error_deg > 0:
        fov = max(fov, 2.4 * error_deg)  # the error circle fits with a margin
    return min(fov, MAX_FOV_DEG)


def covering_surveys(ra: float, dec: float) -> set[str] | None:
    """HiPS IDs (of ours) whose footprint contains the point; None if the MocServer is down."""
    params = {"RA": f"{ra:.4f}", "DEC": f"{dec:.4f}", "SR": "0", "fmt": "json", "get": "id",
              "ID": ",".join(s.hips_id for s in PREFERENCE)}
    try:
        return set(get_net().json(MOCSERVER, params, ttl=30 * 86400.0))
    except (FetchError, ValueError) as exc:
        log.warning("MocServer unavailable (%s); using DSS2", exc)
        return None


def choose_survey(ra: float, dec: float, fov_deg: float) -> Survey:
    if fov_deg > NARROW_FOV_DEG:
        return DSS2
    covered = covering_surveys(ra, dec)
    if covered is None:
        return DSS2
    return next((s for s in PREFERENCE if s.hips_id in covered), DSS2)


def hips2fits_url(hips_id: str, ra: float, dec: float, fov_deg: float, px: int = FULL_PX) -> str:
    q = {"hips": hips_id, "width": px, "height": px, "fov": f"{fov_deg:.6g}", "projection": "TAN",
         "coordsys": "icrs", "ra": f"{ra:.6f}", "dec": f"{dec:.6f}", "format": "jpg"}
    return f"{HIPS2FITS}?{urlencode(q)}"


def _angle(deg: float) -> str:
    if deg >= 1.0:
        return f"{deg:.3g}°"
    if deg >= ARCMIN:
        return f"{deg * 60:.3g}′"
    return f"{deg * 3600:.3g}″"


def sky_context(event: Event) -> list[Image]:
    loc = event["location"]
    if loc.get("frame") != "sky":
        return []
    ra, dec = float(loc["ra_deg"]), float(loc["dec_deg"])  # type: ignore[typeddict-item]
    err = float(loc.get("error_deg") or 0.0)  # type: ignore[union-attr]
    etype = event.get("type", "unknown")
    fov = field_of_view(etype, err)
    survey = choose_survey(ra, dec, fov)
    noun = NOUN.get(etype, "event")
    when = (event.get("observed_at") or "")[:10]

    rough = err * 2.4 >= fov * 0.1  # the error circle is a visible part of the frame
    parts = [
        f"{survey.name} colour image of a {_angle(fov)} square of sky around this {noun}.",
        (f"Crosshair: the {'most likely position' if rough else noun} is at the "
         f"{'' if rough else 'exact '}centre, RA {ra:.5f}°, Dec {dec:+.5f}°."),
    ]
    if etype in MOVING:
        parts.append(f"The {noun} itself is not in this picture: the survey was taken {survey.epoch}, "
                     f"and these are the background stars at its position{' on ' + when if when else ''}.")
    elif etype in MESSENGERS:
        parts.append(f"Archival picture taken {survey.epoch}: the stars and galaxies in the direction the "
                     f"{noun.replace(' source', '')} came from.")
    elif etype in STARS:
        parts.append(f"Archival picture taken {survey.epoch}; the star at the centre is shown as it was "
                     "then, not during this event.")
    else:
        parts.append(f"Archival picture taken {survey.epoch}, before this event, so it shows the field "
                     f"where the {noun} happened, not the {noun} itself.")
    if 2.4 * err > MAX_FOV_DEG:
        parts.append(f"The uncertainty region (radius {_angle(err)}) is larger than this view.")
    elif rough:
        parts.append(f"The true position lies within about {_angle(err)} of the centre.")

    c = survey.credit
    return [Image(url=hips2fits_url(survey.hips_id, ra, dec, fov), kind="sky_context", caption=" ".join(parts),
                  credit=c.credit, license=c.license, width=FULL_PX, height=FULL_PX)]

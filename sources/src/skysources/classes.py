"""Broker labels -> CatchType. One place, so the mapping table in README.md stays honest.

Anything not listed maps to "unknown". A label that only says "galaxy" or "star" is a
cross-match of the host/position, not a type of event, so it never overrides the classifier.
"""

from __future__ import annotations

import re

from .models import CatchType

# --- Fink CATS classifier (f:clf_cats_class / f:main_label_classifier), score in f:clf_cats_score.
# Codes from the Fink schema endpoint (/api/v1/schema) and https://arxiv.org/abs/2404.08798.
FINK_CATS: dict[int, tuple[str, CatchType]] = {
    -1: ("not processed", "unknown"),
    11: ("SN-like", "supernova"),
    12: ("Fast (e.g. kilonova, microlensing, nova)", "unknown"),  # mixed bag: no single type
    13: ("Long (e.g. superluminous SN, TDE)", "unknown"),  # mixed bag: no single type
    21: ("Periodic (e.g. RR Lyrae, eclipsing binary)", "variable_star"),
    22: ("Non-periodic (e.g. AGN)", "active_galaxy"),
}

# --- TNS type (f:xm_tns_type): a reported classification, checked by prefix, first match wins.
TNS_PREFIX: list[tuple[str, CatchType]] = [
    ("SLSN", "supernova"),
    ("SN", "supernova"),
    ("TDE", "tidal_disruption_event"),
    ("Kilonova", "kilonova"),
    ("AGN", "active_galaxy"),
    ("QSO", "active_galaxy"),
    ("Blazar", "active_galaxy"),
    ("M dwarf", "flare"),  # "M dwarf flare"
    ("Nova", "variable_star"),
    ("CV", "variable_star"),
    ("LBV", "variable_star"),
    ("Varstar", "variable_star"),
    ("Microlens", "microlensing"),
]

# --- SIMBAD otype (f:xm_simbad_otype, closest SIMBAD source within 1 arcsec).
# Codes: https://simbad.cds.unistra.fr/guide/otypes.htx
SIMBAD: dict[str, CatchType] = {
    **dict.fromkeys(["SN*", "SN?"], "supernova"),
    **dict.fromkeys(
        ["QSO", "Q?", "AGN", "AG?", "Sy1", "Sy2", "SyG", "Sy?", "Bla", "Bz?", "BLL", "BL?", "LIN", "LI?"],
        "active_galaxy",
    ),
    **dict.fromkeys(["EB*", "EB?", "El*", "El?"], "eclipsing_binary"),
    **dict.fromkeys(["Fl*", "Fl?"], "flare"),
    **dict.fromkeys(["Lev", "LeI"], "microlensing"),
    **dict.fromkeys(["Pl", "Pl?"], "planet_candidate"),
    **dict.fromkeys(
        [
            "V*", "V*?", "RR*", "RR?", "Ce*", "Ce?", "cC*", "C?*", "dS*", "LP*", "LP?", "Mi*", "Mi?",
            "sr*", "Ro*", "BY*", "BY?", "RS*", "RS?", "Pu*", "Pu?", "WV*", "WV?", "gD*", "Ir*",
            "Or*", "Er*", "Er?", "CV*", "CV?", "No*", "No?", "RI*", "bC*", "sg*", "s*b", "SX*",
            "ZZ*", "a2*", "AM*", "AM?", "DN*", "NL*", "Y*O", "TT*", "TT?", "Ae*", "Ae?", "LM*",
            "Be*", "Be?", "BS*", "HB*", "WR*", "LB*", "LBV", "RC*", "RC?", "Mira",
        ],
        "variable_star",
    ),
}

# --- VSX variable-star type (f:xm_vsx_Type). https://www.aavso.org/vsx/index.php?view=about.vartypes
_VSX_ECLIPSING = re.compile(r"^(E|EA|EB|EW|EP|ELL|ED|ESD|EC|EL)(\b|[:/+|])")
_VSX_FLARE = re.compile(r"^(UV|UVN|FLARE)(\b|[:/+|])")

# --- ALeRCE LSST stamp classifier (stamp_classifier_rubin_beta_20260421), used for the heatmap.
ALERCE_STAMP: dict[str, CatchType | None] = {
    "SN": "supernova",
    "AGN": "active_galaxy",
    "VS": "variable_star",
    "asteroid": "asteroid",
    "bogus": None,  # artefact: dropped, not counted
}

# --- SkyBoT dynamical class (IMCCE). Hierarchical strings, e.g. "MB>Inner", "NEA>Apollo",
# "KBO>Resonant>3:2". First matching prefix wins. We query SkyBoT for asteroids and comets only
# (no planets), so an unlisted class is still a small body: "asteroid" unless the name is a comet's.
SKYBOT_CLASS_MAP: list[tuple[str, CatchType]] = [
    ("NEA", "near_earth_object"),  # Atira / Aten / Apollo / Amor
    ("KBO", "trans_neptunian_object"),  # Classical / Resonant / SDO / Detached
    ("TNO", "trans_neptunian_object"),
    ("Comet", "comet"),
    ("MB", "asteroid"),
    ("Hungaria", "asteroid"),
    ("Mars-Crosser", "asteroid"),
    ("Trojan", "asteroid"),
    ("Centaur", "asteroid"),
]

# Designations like 1I/'Oumuamua, 2I/Borisov, 3I/ATLAS.
_INTERSTELLAR = re.compile(r"^\d+I/")


def skybot_class_to_catch_type(skybot_class: str, name: str = "") -> CatchType:
    if _INTERSTELLAR.match(name or ""):
        return "interstellar_object"
    for prefix, catch in SKYBOT_CLASS_MAP:
        if skybot_class.startswith(prefix):
            return catch
    if re.match(r"^(C|P|D|X)/|^\d+P", name or ""):
        return "comet"
    return "asteroid"


_EMPTY = {"", "nan", "none", "null", "fail", "unknown"}


def present(value: object) -> str | None:
    """Fink fills missing cross-matches with 'Fail', 'nan' or null."""
    if value is None:
        return None
    s = str(value).strip()
    return None if s.lower() in _EMPTY else s


def tns_type(label: str | None) -> CatchType | None:
    if not (label := present(label)):
        return None
    for prefix, catch in TNS_PREFIX:
        if label.startswith(prefix):
            return catch
    return None


def simbad_type(otype: str | None) -> CatchType | None:
    if not (otype := present(otype)):
        return None
    return SIMBAD.get(otype)


def vsx_type(vtype: str | None) -> CatchType | None:
    if not (vtype := present(vtype)):
        return None
    if _VSX_ECLIPSING.match(vtype):
        return "eclipsing_binary"
    if _VSX_FLARE.match(vtype):
        return "flare"
    return "variable_star"


def cats_type(code: object) -> tuple[str, CatchType]:
    try:
        return FINK_CATS.get(int(code), ("unrecognised code", "unknown"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return FINK_CATS[-1]

"""Checks for the SHARED CONTRACT shapes, used by several test files."""

import json
from datetime import datetime

from skysources.models import CATCH_TYPES

DISCOVERY_KEYS = {
    "id", "type", "confidence", "source", "origin", "ra_deg", "dec_deg", "detected_at",
    "name_if_known", "known_status", "cutouts", "light_curve", "explanation", "links", "raw",
}


def assert_discovery(d: dict) -> None:
    assert set(d) == DISCOVERY_KEYS, set(d) ^ DISCOVERY_KEYS
    assert d["id"].startswith(("rubin:obj:", "rubin:ss:"))
    assert d["type"] in CATCH_TYPES
    assert 0.0 <= d["confidence"] <= 1.0
    assert d["source"] == "rubin"
    assert 0 <= d["ra_deg"] < 360 and -90 <= d["dec_deg"] <= 90
    assert datetime.fromisoformat(d["detected_at"]).tzinfo is not None
    assert d["known_status"] in ("known", "not_on_lists", "unchecked")
    assert set(d["cutouts"]) == {"before", "now", "difference"}
    for link in d["links"]:
        assert set(link) == {"label", "url"} and link["url"].startswith("https://")
    assert "discover" not in d["explanation"].lower()  # honesty rule
    assert isinstance(d["raw"], dict) and d["raw"]["alert_count"] >= 1
    json.dumps(d, allow_nan=False)  # strict JSON: browsers reject NaN


def assert_heatmap(h: dict) -> None:
    assert set(h) == {"generated_at", "grid", "window", "cells"}
    assert datetime.fromisoformat(h["window"]["start"]) < datetime.fromisoformat(h["window"]["end"])
    assert h["grid"].startswith("healpix nside=")
    nside = int(h["grid"].split("=")[1])
    datetime.fromisoformat(h["generated_at"])
    pixes = [c["pix"] for c in h["cells"]]
    assert pixes == sorted(set(pixes))
    for c in h["cells"]:
        assert set(c) == {"pix", "counts"}
        assert 0 <= c["pix"] < 12 * nside * nside
        assert c["counts"] and all(k in CATCH_TYPES and v > 0 for k, v in c["counts"].items())

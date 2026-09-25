"""Keep api/ in step with contracts/: CONTRACT.md field lists and generated JSON Schemas."""

from __future__ import annotations

import re
from pathlib import Path

from api.contract import CatchType, Discovery, Forecast, Heatmap, Sphere
from api.export_schemas import SCHEMA_DIR, render

CONTRACT = (Path(__file__).resolve().parents[2] / "contracts" / "CONTRACT.md").read_text()


def _block(name: str) -> str:
    """The text after `name =` up to the next top-level `X =` line."""
    m = re.search(rf"^{re.escape(name)} = (.*?)(?=^\S+ = |^Honesty rule)", CONTRACT, re.S | re.M)
    assert m, name
    return m.group(1)


def _top_level_keys(text: str) -> list[str]:
    depth, keys, token = 0, [], ""
    for ch in text.strip()[1:-1]:
        if ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
        if depth == 0 and ch == ",":
            keys.append(token)
            token = ""
        elif depth == 0:
            token += ch
    keys.append(token)
    return [re.split(r"[\s{\[]", k.strip())[0] for k in keys if k.strip()]


def test_catch_types_match_contract():
    names = re.findall(r"[a-z_]+", _block("CatchType"))
    assert names == [t.value for t in CatchType]


def test_discovery_fields_match_contract():
    assert _top_level_keys(_block("Discovery")) == list(Discovery.model_fields)


def test_forecast_fields_match_contract():
    assert _top_level_keys(_block("Forecast")) == list(Forecast.model_fields)


def test_sphere_and_heatmap_fields_match_contract():
    assert _top_level_keys(_block("Sphere")) == list(Sphere.model_fields)
    assert _top_level_keys(_block("heatmap.json")) == list(Heatmap.model_fields)


def test_generated_schemas_are_up_to_date():
    for filename, text in render().items():
        path = SCHEMA_DIR / filename
        assert path.exists(), f"run: uv run python -m api.export_schemas ({filename} missing)"
        assert path.read_text() == text, f"run: uv run python -m api.export_schemas ({filename})"

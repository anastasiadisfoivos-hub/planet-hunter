"""Honesty rule from the contract: never "new planet" or "discovered"."""

from __future__ import annotations

import re
from typing import Any

from api.contract import Discovery

BANNED = re.compile(r"new\s+planets?|discovered", re.IGNORECASE)

_REPLACEMENTS = (
    (re.compile(r"new\s+planets", re.IGNORECASE), "planet candidates"),
    (re.compile(r"new\s+planet", re.IGNORECASE), "planet candidate"),
    (re.compile(r"undiscovered", re.IGNORECASE), "not yet catalogued"),
    (re.compile(r"discovered", re.IGNORECASE), "detected"),
)


def soften(text: str) -> str:
    for pattern, replacement in _REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def clean(d: Discovery) -> Discovery:
    """Rewrite player-facing text from upstream modules so it follows the rule."""
    return d.model_copy(
        update={
            "explanation": soften(d.explanation),
            "links": [link.model_copy(update={"label": soften(link.label)}) for link in d.links],
        }
    )


def violations(obj: Any, path: str = "$") -> list[str]:
    """Every string value (not key) that breaks the rule, with its JSON path. Skips `raw`."""
    found: list[str] = []
    if isinstance(obj, str):
        if BANNED.search(obj):
            found.append(f"{path}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if k != "raw":
                found.extend(violations(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(violations(v, f"{path}[{i}]"))
    return found

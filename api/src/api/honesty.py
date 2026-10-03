"""Honesty rule for everything the API says: never "new planet" or "discovered".

Upstream text is rewritten when it is stored (events at ingest, analyses when computed), and the
tests scan every JSON response with violations(). `raw` blobs and URLs are left alone: they are
data from the source, not our wording, and rewriting a URL would break it.
"""

from __future__ import annotations

import re
from typing import Any

BANNED = re.compile(r"new\s+planets?|discovered", re.IGNORECASE)

_REPLACEMENTS = (
    (re.compile(r"new\s+planets", re.IGNORECASE), "planet candidates"),
    (re.compile(r"new\s+planet", re.IGNORECASE), "planet candidate"),
    (re.compile(r"undiscovered", re.IGNORECASE), "not yet catalogued"),
    (re.compile(r"discovered", re.IGNORECASE), "detected"),
)


def _skip(key: str) -> bool:
    return key == "raw" or key == "url" or key.endswith("_url")


def soften(text: str) -> str:
    for pattern, replacement in _REPLACEMENTS:
        text = pattern.sub(replacement, text)
    return text


def clean(obj: Any) -> Any:
    """A copy of a JSON value with every string (except raw and URLs) softened."""
    if isinstance(obj, str):
        return soften(obj)
    if isinstance(obj, dict):
        return {k: (v if _skip(k) else clean(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj


def violations(obj: Any, path: str = "$") -> list[str]:
    """Every string value (not key) that breaks the rule, with its JSON path."""
    found: list[str] = []
    if isinstance(obj, str):
        if BANNED.search(obj):
            found.append(f"{path}: {obj!r}")
    elif isinstance(obj, dict):
        for k, v in obj.items():
            if not _skip(k):
                found.extend(violations(v, f"{path}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            found.extend(violations(v, f"{path}[{i}]"))
    return found

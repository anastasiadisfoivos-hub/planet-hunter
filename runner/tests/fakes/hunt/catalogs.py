from __future__ import annotations

import json
from pathlib import Path


class Catalogue:
    def __init__(self, entries=None):
        self.entries = entries or []

    def on_star(self, tic):
        return []

    def to_json(self, path: Path) -> None:
        Path(path).write_text(json.dumps({"fetched_at": None, "entries": []}))

    @classmethod
    def from_json(cls, path: Path) -> Catalogue:
        json.loads(Path(path).read_text())
        return cls()


def load(refresh: bool = False) -> Catalogue:
    return Catalogue()

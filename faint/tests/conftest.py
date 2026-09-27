import json
from pathlib import Path

import pytest

from skyfaint.tglc import FaintLC

DATA = Path(__file__).parent / "data"


@pytest.fixture(scope="session")
def facts() -> dict:
    return json.loads((DATA / "facts.json").read_text())


def load(tic: int) -> tuple[FaintLC, dict]:
    """A recorded light curve and its TIC row."""
    return FaintLC.load(DATA / f"{tic}.npz"), json.loads((DATA / f"{tic}.json").read_text())["star"]

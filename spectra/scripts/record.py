"""Re-record the test fixtures from the live services (needs network; ~2 minutes).

    uv run python scripts/record.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from recording import recording
from sample import ELEMENTS, HOSTNAMES, PLANETS, SUN_RANGE, TICS

from skyspectra.build import build
from skyspectra.net import Net


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp, recording("sample", {"hostnames": HOSTNAMES, "planets": PLANETS}):
        index = build(Path(tmp), Net(), TICS, element_symbols=ELEMENTS, sun_range=SUN_RANGE,
                      planets=sorted(PLANETS))
        print(index["counts"])


if __name__ == "__main__":
    main()

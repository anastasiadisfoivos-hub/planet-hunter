import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).parent))

from recording import install_replay


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    """Tests never touch the network or the user's cache."""
    monkeypatch.setenv("SKYSPECTRA_CACHE", str(tmp_path / "cache"))

    def blocked(*args, **kwargs):
        raise AssertionError("network access in tests")

    monkeypatch.setattr(httpx.Client, "send", blocked)


@pytest.fixture
def replay(monkeypatch):
    install_replay(monkeypatch, "sample")

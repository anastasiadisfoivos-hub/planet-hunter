import os

import pytest

from skyvet import cache


@pytest.fixture(autouse=True, scope="session")
def no_network():
    """The tests are offline: any socket connection fails (the TRICERATOPS child process does the same when
    SKYVET_OFFLINE is set)."""
    os.environ.setdefault("SKYVET_OFFLINE", "1")
    cache.forbid_network()

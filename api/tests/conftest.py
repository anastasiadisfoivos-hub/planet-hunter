from __future__ import annotations

import time
import uuid
from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api import honesty
from api.app import create_app
from api.fakes.forecast import FakeForecaster
from api.fakes.rubin import FakeAlertSource
from api.fakes.tess import FakeStarHunter
from api.ratelimit import RateLimiter
from api.settings import Settings
from api.storage.sqlite import SqliteStorage
from api.wiring import Services

# A patch of sky where the fake Rubin source reliably has objects.
SKY = {"ra_deg": 150.0, "dec_deg": -20.0, "radius_deg": 3.0}
TIC = 25155310


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class HonestClient(TestClient):
    """Fails the test if any JSON response breaks the contract's honesty rule."""

    def request(self, *args, **kwargs):
        response = super().request(*args, **kwargs)
        if response.headers.get("content-type", "").startswith("application/json"):
            bad = honesty.violations(response.json())
            assert not bad, f"honesty rule broken: {bad}"
        return response


@pytest.fixture
def services() -> Services:
    return Services(
        storage=SqliteStorage(":memory:"),
        alerts=FakeAlertSource(),
        hunter=FakeStarHunter(),
        forecaster=FakeForecaster(),
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(db_path=":memory:")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def make_client(services, settings, clock):
    clients: list[TestClient] = []

    def make(**overrides) -> HonestClient:
        app = create_app(replace(settings, **overrides), services, RateLimiter(clock=clock))
        client = HonestClient(app)
        client.__enter__()
        clients.append(client)
        return client

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client) -> Iterator[HonestClient]:
    return make_client()


def player() -> dict[str, str]:
    return {"X-Player-Id": str(uuid.uuid4())}


@pytest.fixture
def alice() -> dict[str, str]:
    return player()


@pytest.fixture
def bob() -> dict[str, str]:
    return player()


def wait_job(client: TestClient, job_id: str, headers: dict, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}", headers=headers).json()
        if body["status"] in ("done", "failed"):
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s: {body}")


def wait_until(predicate, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.01)
    raise AssertionError("condition not met in time")

from __future__ import annotations

import os
import shutil
import subprocess
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


# Every test that touches storage runs once per backend. PH_TEST_BACKENDS=sqlite (or postgres)
# narrows it. Postgres comes from PH_TEST_DATABASE_URL (a throwaway database: tests wipe it), or
# else a disposable `postgres:16` Docker container started for the session.
BACKENDS = [b.strip() for b in os.environ.get("PH_TEST_BACKENDS", "sqlite,postgres").split(",")]
TABLES = "traps, discoveries, catches, jobs"


def _start_postgres_container() -> tuple[str, str]:
    if not shutil.which("docker"):
        pytest.skip("Postgres tests need Docker or PH_TEST_DATABASE_URL")
    run = subprocess.run(
        [
            "docker", "run", "-d", "--rm",
            "-e", "POSTGRES_PASSWORD=ph", "-e", "POSTGRES_DB=ph",
            "-p", "127.0.0.1::5432",
            "--tmpfs", "/var/lib/postgresql/data",
            "postgres:16", "-c", "fsync=off", "-c", "full_page_writes=off",
        ],
        capture_output=True,
        text=True,
    )  # fmt: skip
    if run.returncode != 0:
        pytest.skip(f"could not start a Postgres container: {run.stderr.strip()}")
    cid = run.stdout.strip()
    ports = subprocess.run(
        ["docker", "port", cid, "5432/tcp"], capture_output=True, text=True, check=True
    )
    port = ports.stdout.splitlines()[0].rsplit(":", 1)[1]
    return cid, f"postgresql://postgres:ph@127.0.0.1:{port}/ph"


@pytest.fixture(scope="session")
def pg_url() -> Iterator[str]:
    import psycopg

    url, cid = os.environ.get("PH_TEST_DATABASE_URL"), None
    if not url:
        cid, url = _start_postgres_container()
    try:
        deadline = time.monotonic() + 60
        while True:
            try:
                psycopg.connect(url, connect_timeout=2).close()
                break
            except psycopg.OperationalError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(0.2)
        with psycopg.connect(url, autocommit=True) as conn:
            conn.execute(f"DROP TABLE IF EXISTS {TABLES}, schema_migrations CASCADE")
        yield url
    finally:
        if cid:
            subprocess.run(["docker", "rm", "-f", cid], capture_output=True)


@pytest.fixture(scope="session")
def pg_storage(pg_url):
    from api.storage.postgres import PostgresStorage

    storage = PostgresStorage(pg_url, pool_max=8)
    yield storage
    storage.close()


def wipe_postgres(url: str) -> None:
    import psycopg

    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE")


@pytest.fixture(params=BACKENDS)
def backend(request) -> str:
    return request.param


@pytest.fixture
def storage(backend, request):
    if backend == "sqlite":
        s = SqliteStorage(":memory:")
        yield s
        s.close()
    elif backend == "postgres":
        pg = request.getfixturevalue("pg_storage")  # migrates on first use
        wipe_postgres(request.getfixturevalue("pg_url"))
        yield pg
    else:
        raise ValueError(f"unknown backend {backend!r} in PH_TEST_BACKENDS")


@pytest.fixture
def services(storage) -> Services:
    return Services(
        storage=storage,
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

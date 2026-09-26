from __future__ import annotations

import os
import shutil
import subprocess
import time
from collections.abc import Iterator
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from api import honesty
from api.app import create_app
from api.fakes.archive import FakeArchive
from api.fakes.tess import FakeAnalyzer
from api.ratelimit import RateLimiter
from api.settings import Settings
from api.storage.sqlite import SqliteStorage
from api.wiring import Services

TIC = 25155310


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0

    def __call__(self) -> float:
        return self.t


class HonestClient(TestClient):
    """Fails the test if any JSON response breaks the honesty rule."""

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
TABLES = (
    "events, event_sources, ingest_status, star_analyses, star_names, analyze_jobs,"
    " star_lightcurves, known_planets, candidates, pixel_vets, votes, sensitivity, finder_sweep"
)
OLD_TABLES = "traps, discoveries, catches, jobs"


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
            conn.execute(f"DROP TABLE IF EXISTS {TABLES}, {OLD_TABLES}, schema_migrations CASCADE")
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
    return Services(storage=storage, analyzer=FakeAnalyzer(), archive=FakeArchive())


@pytest.fixture
def settings() -> Settings:
    # Generous limits here; tests/test_ratelimit.py checks the real ones.
    return Settings(db_path=":memory:", rate_read_per_min=10_000, rate_analyze_per_min=10_000)


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
def client(make_client) -> HonestClient:
    return make_client()


def wait_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    body: dict = {}
    while time.monotonic() < deadline:
        body = client.get(f"/jobs/{job_id}").json()
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

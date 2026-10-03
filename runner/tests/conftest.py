"""Fixtures: a fake install (venvs whose python sees tests/fakes' hunt / skyvet), and the real API served locally.

The API is the repo's own api/ (FastAPI + SQLite), started with uvicorn in api's venv (`uv sync --project api`
builds it on first use). Nothing here touches the network beyond localhost."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import pytest

RUNNER = Path(__file__).resolve().parents[1]
REPO = RUNNER.parent
FAKES = Path(__file__).resolve().parent / "fakes"
TOKEN = "test-ingest-token"


def api_python() -> Path:
    env_py = os.environ.get("PH_TEST_API_PYTHON")
    if env_py:
        return Path(env_py)
    py = REPO / "api" / ".venv" / "bin" / "python"
    if not py.exists():
        subprocess.run(["uv", "sync", "--project", str(REPO / "api"), "--quiet"], check=True)
    return py


def _wrapper(path: Path, python: str, pythonpath: str | None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pp = f'PYTHONPATH="{pythonpath}:$PYTHONPATH" ' if pythonpath else ""
    path.write_text(f'#!/bin/sh\n{pp}exec "{python}" "$@"\n')
    path.chmod(0o755)


@pytest.fixture
def install(tmp_path) -> dict:
    """PH_HOME with venvs/{hunt,faint,vet,api}/bin/python and a repo/ that has hunt/ and faint/ folders."""
    home, data = tmp_path / "home", tmp_path / "data"
    for name in ("hunt", "faint"):
        _wrapper(home / "venvs" / name / "bin" / "python", sys.executable, str(FAKES))
    _wrapper(home / "venvs" / "vet" / "bin" / "python", sys.executable, str(FAKES))
    _wrapper(home / "venvs" / "api" / "bin" / "python", str(api_python()), None)
    (home / "repo").mkdir()
    for name in ("api", "hunt", "runner"):
        (home / "repo" / name).symlink_to(REPO / name)
    (home / "repo" / "faint").mkdir()  # faint/ is on the ref: the faint queue is on
    return {"home": home, "data": data}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Api:
    def __init__(self, url: str, db: Path, proc: subprocess.Popen):
        self.url, self.db, self.proc = url, db, proc

    def get(self, path: str) -> dict:
        with urllib.request.urlopen(self.url + path, timeout=10) as r:
            return json.loads(r.read())


@pytest.fixture
def api(tmp_path):
    port = _free_port()
    db = tmp_path / "api.db"
    env = {**os.environ, "PH_DB_PATH": str(db), "PH_INGEST_TOKEN": TOKEN, "PH_RATE_READ_PER_MIN": "10000",
           "PH_RATE_INGEST_PER_MIN": "10000"}
    env.pop("PH_DATABASE_URL", None)
    proc = subprocess.Popen([str(api_python()), "-m", "uvicorn", "--factory", "api.app:create_app", "--port", str(port),
                             "--log-level", "warning"], cwd=REPO / "api", env=env)
    url = f"http://127.0.0.1:{port}"
    for _ in range(150):
        try:
            urllib.request.urlopen(url + "/healthz", timeout=1).read()
            break
        except OSError:
            time.sleep(0.1)
    else:
        proc.kill()
        raise RuntimeError("API did not start")
    yield Api(url, db, proc)
    proc.terminate()
    proc.wait(10)

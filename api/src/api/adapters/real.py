"""Real adapters: one per sibling module. Each wraps that module so it satisfies a port in
api/ports.py. They are stubs until sources/, pipeline/ and forecast/ publish their packages.

To wire one in:
  1. add the sibling package as a path dependency in api/pyproject.toml, e.g.
     `planet-hunter-sources = { path = "../sources", editable = true }` under [tool.uv.sources];
  2. replace the stub below with a class that calls it and returns contract models;
  3. run the same test suite with that adapter via tests/test_ports_conformance.py.
"""

from __future__ import annotations

from api.ports import AlertSource, Forecaster, StarHunter


def _missing(module: str, port: str) -> NotImplementedError:
    return NotImplementedError(
        f"The real {port} needs {module}/, which isn't wired in yet. Use PH_ADAPTERS=fake."
    )


def alert_source() -> AlertSource:
    raise _missing("sources", "AlertSource")


def star_hunter() -> StarHunter:
    raise _missing("pipeline", "StarHunter")


def forecaster() -> Forecaster:
    raise _missing("forecast", "Forecaster")

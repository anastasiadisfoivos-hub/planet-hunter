"""Settings, all from the environment. On the server systemd loads /etc/planet-hunter.env (root-only, chmod 600)
into the service's environment; nothing secret is ever written anywhere else."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

QUEUES = ("fast", "deep", "faint")
# Share of worker-seconds each search queue gets in a night (the nightly split; queues.pick_queue enforces it).
DEFAULT_SPLIT = {"fast": 0.45, "deep": 0.40, "faint": 0.15}
# Per-star wall-clock limits. Fast: 3 sectors, BLS only. Deep: every sector (a 40-sector continuous-viewing-zone
# star took ~400 s on a CI runner in DEEPHUNT's tests; a 4-core Ampere core is slower). Faint: TGLC + deep search.
DEFAULT_TIMEOUT_S = {"fast": 600, "deep": 2400, "faint": 1800, "vet": 1800}


def _int(env: dict, name: str, default: int) -> int:
    return int(env.get(name) or default)


def _float(env: dict, name: str, default: float) -> float:
    return float(env.get(name) or default)


def parse_split(text: str | None) -> dict[str, float]:
    """"fast=45,deep=40,faint=15" -> shares that add up to 1. Queues left out get 0 (never picked)."""
    if not text:
        return dict(DEFAULT_SPLIT)
    raw: dict[str, float] = {}
    for part in text.split(","):
        name, _, value = part.strip().partition("=")
        if name not in QUEUES:
            raise ValueError(f"PH_SPLIT: unknown queue {name!r} (queues: {', '.join(QUEUES)})")
        raw[name] = float(value)
    total = sum(raw.values())
    if total <= 0:
        raise ValueError("PH_SPLIT: the shares add up to 0")
    return {q: raw.get(q, 0.0) / total for q in QUEUES}


@dataclass(frozen=True)
class Config:
    home: Path = Path("/opt/planet-hunter")  # repo/ (read-only clone) and venvs/
    data: Path = Path("/var/lib/planet-hunter")  # ledger, runs, targets, caches
    api_url: str | None = None
    ingest_token: str | None = field(default=None, repr=False)
    db_path: str | None = None  # tests and dry runs only: finder_ingest into this SQLite file instead of the API
    repo_url: str = "https://github.com/anastasiadisfoivos-hub/planet-hunter.git"
    repo_ref: str = "main"
    workers: int = 4
    split: dict[str, float] = field(default_factory=lambda: dict(DEFAULT_SPLIT))
    run_start_utc: str = "00:15"  # a search day starts here (the timer fires then)
    search_hours: float = 21.5  # stop starting new stars this long after the day's start
    wrap_hours: float = 2.0  # merge + vet the rest + ingest must fit in this
    disk_cap_gb: float = 150.0  # everything under `data` stays below this
    star_limit: int | None = None  # at most this many stars per queue per run (dry runs)
    vet: bool = True
    vet_slots: int = 1  # at most this many of the workers vet at once; the rest keep searching
    tri_budget_s: int = 600
    targets_max_age_days: float = 7.0
    auto_update: bool = True
    timeouts: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_TIMEOUT_S))
    heartbeat_s: float = 120.0
    targets_file: Path | None = None  # override the ranked bright-star list (dry run)
    faint_file: Path | None = None  # override the faint list

    @property
    def repo(self) -> Path:
        return self.home / "repo"

    def venv_python(self, name: str) -> Path:
        return self.home / "venvs" / name / "bin" / "python"

    @property
    def ledger_path(self) -> Path:
        return self.data / "ledger.sqlite"

    @property
    def runs_dir(self) -> Path:
        return self.data / "runs"

    @property
    def cache_dir(self) -> Path:
        return self.data / "cache"

    @property
    def targets_dir(self) -> Path:
        return self.data / "targets"

    @property
    def state_dir(self) -> Path:
        return self.data / "state"

    def cache_env(self) -> dict[str, str]:
        """Every package's cache inside `data/cache`, so the disk janitor sees (and can cap) all of it."""
        c = self.cache_dir
        return {
            "HUNT_CACHE_DIR": str(c / "hunt"),
            "HUNTER_CACHE_DIR": str(c / "pipeline"),
            "FAINT_CACHE_DIR": str(c / "faint"),
            "SKYVET_CACHE_DIR": str(c / "vet"),
            "SKYVET_WORK_DIR": str(c / "vet-work"),
            "SKYPIXELS_CACHE_DIR": str(c / "pixels"),
            "XDG_CACHE_HOME": str(c / "xdg"),  # astropy, astroquery
            "LIGHTKURVE_CACHE_DIR": str(c / "lightkurve"),
            "MPLCONFIGDIR": str(c / "matplotlib"),
        }

    @classmethod
    def from_env(cls, env: dict | None = None) -> Config:
        env = dict(os.environ if env is None else env)
        timeouts = dict(DEFAULT_TIMEOUT_S)
        for q in timeouts:
            timeouts[q] = _int(env, f"PH_{q.upper()}_TIMEOUT_S", timeouts[q])
        limit = env.get("PH_STAR_LIMIT")
        return cls(
            home=Path(env.get("PH_HOME") or "/opt/planet-hunter"),
            data=Path(env.get("PH_DATA") or "/var/lib/planet-hunter"),
            api_url=(env.get("PH_API_URL") or "").rstrip("/") or None,
            ingest_token=env.get("PH_INGEST_TOKEN") or None,
            db_path=env.get("PH_DB_PATH") or None,
            repo_url=env.get("PH_REPO_URL") or cls.repo_url,
            repo_ref=env.get("PH_REPO_REF") or cls.repo_ref,
            workers=_int(env, "PH_WORKERS", 4),
            split=parse_split(env.get("PH_SPLIT")),
            run_start_utc=env.get("PH_RUN_START_UTC") or "00:15",
            search_hours=_float(env, "PH_SEARCH_HOURS", 21.5),
            wrap_hours=_float(env, "PH_WRAP_HOURS", 2.0),
            disk_cap_gb=_float(env, "PH_DISK_CAP_GB", 150.0),
            star_limit=int(limit) if limit else None,
            vet=(env.get("PH_VET") or "1") != "0",
            vet_slots=_int(env, "PH_VET_SLOTS", 1),
            tri_budget_s=_int(env, "PH_TRI_BUDGET_S", 600),
            targets_max_age_days=_float(env, "PH_TARGETS_MAX_AGE_DAYS", 7.0),
            auto_update=(env.get("PH_AUTO_UPDATE") or "1") != "0",
            timeouts=timeouts,
            heartbeat_s=_float(env, "PH_HEARTBEAT_S", 120.0),
            targets_file=Path(env["PH_TARGETS_FILE"]) if env.get("PH_TARGETS_FILE") else None,
            faint_file=Path(env["PH_FAINT_FILE"]) if env.get("PH_FAINT_FILE") else None,
        )

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    db_path: str = "traps.db"
    # Postgres URL; when set it replaces SQLite. Kept out of repr: it holds the password.
    database_url: str | None = field(default=None, repr=False)
    db_pool_max: int = 5
    db_timeout_s: float = 5.0
    db_statement_timeout_ms: int = 15000
    adapters: str = "fake"  # "fake" | "real"
    max_concurrent_hunts: int = 2
    sweep_nights: int = 7
    sweep_timeout_s: float = 15.0
    hunt_timeout_s: float = 300.0
    max_traps_per_player: int = 50
    max_pending_jobs_per_player: int = 3
    # Requests per minute; each bucket allows this many in a burst, then refills evenly.
    rate_all_per_min: int = 120
    rate_trap_create_per_min: int = 20
    rate_hunt_per_min: int = 6
    rate_ip_per_min: int = 600
    cors_origins: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("PH_CORS_ORIGINS", "")
        return cls(
            db_path=os.environ.get("PH_DB_PATH", "traps.db"),
            database_url=os.environ.get("PH_DATABASE_URL") or None,
            db_pool_max=_int("PH_DB_POOL_MAX", 5),
            db_timeout_s=_float("PH_DB_TIMEOUT_S", 5.0),
            db_statement_timeout_ms=_int("PH_DB_STATEMENT_TIMEOUT_MS", 15000),
            adapters=os.environ.get("PH_ADAPTERS", "fake"),
            max_concurrent_hunts=_int("PH_MAX_CONCURRENT_HUNTS", 2),
            sweep_timeout_s=_float("PH_SWEEP_TIMEOUT_S", 15.0),
            hunt_timeout_s=_float("PH_HUNT_TIMEOUT_S", 300.0),
            max_traps_per_player=_int("PH_MAX_TRAPS_PER_PLAYER", 50),
            max_pending_jobs_per_player=_int("PH_MAX_PENDING_JOBS_PER_PLAYER", 3),
            rate_all_per_min=_int("PH_RATE_ALL_PER_MIN", 120),
            rate_trap_create_per_min=_int("PH_RATE_TRAP_CREATE_PER_MIN", 20),
            rate_hunt_per_min=_int("PH_RATE_HUNT_PER_MIN", 6),
            rate_ip_per_min=_int("PH_RATE_IP_PER_MIN", 600),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        )

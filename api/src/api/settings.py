from __future__ import annotations

import os
from dataclasses import dataclass, field


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def _float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


@dataclass(frozen=True)
class Settings:
    db_path: str = "spotter.db"
    # Postgres URL; when set it replaces SQLite. Kept out of repr: it holds the password.
    database_url: str | None = field(default=None, repr=False)
    db_pool_max: int = 5
    db_timeout_s: float = 5.0
    db_statement_timeout_ms: int = 15000
    adapters: str = "fake"  # "fake" | "real"
    # Analyze a star
    max_concurrent_hunts: int = 2
    max_queued_jobs: int = 50
    hunt_timeout_s: float = 600.0
    marker_ttl_s: float = 21600.0  # ask MAST for a star's newest sector at most this often
    marker_timeout_s: float = 10.0
    resolve_timeout_s: float = 20.0
    # Requests per minute per client IP; each bucket allows this many in a burst, then refills.
    rate_read_per_min: int = 120
    rate_analyze_per_min: int = 6
    # How many proxies in front of the API append to X-Forwarded-For (Render: 1). 0 = ignore it.
    trusted_proxy_hops: int = 0
    web_origins: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_env(cls) -> Settings:
        origins = os.environ.get("PH_WEB_ORIGIN", "")
        return cls(
            db_path=os.environ.get("PH_DB_PATH", "spotter.db"),
            database_url=os.environ.get("PH_DATABASE_URL") or None,
            db_pool_max=_int("PH_DB_POOL_MAX", 5),
            db_timeout_s=_float("PH_DB_TIMEOUT_S", 5.0),
            db_statement_timeout_ms=_int("PH_DB_STATEMENT_TIMEOUT_MS", 15000),
            adapters=os.environ.get("PH_ADAPTERS", "fake"),
            max_concurrent_hunts=_int("PH_MAX_CONCURRENT_HUNTS", 2),
            max_queued_jobs=_int("PH_MAX_QUEUED_JOBS", 50),
            hunt_timeout_s=_float("PH_HUNT_TIMEOUT_S", 600.0),
            marker_ttl_s=_float("PH_MARKER_TTL_S", 21600.0),
            marker_timeout_s=_float("PH_MARKER_TIMEOUT_S", 10.0),
            resolve_timeout_s=_float("PH_RESOLVE_TIMEOUT_S", 20.0),
            rate_read_per_min=_int("PH_RATE_READ_PER_MIN", 120),
            rate_analyze_per_min=_int("PH_RATE_ANALYZE_PER_MIN", 6),
            trusted_proxy_hops=_int("PH_TRUSTED_PROXY_HOPS", 0),
            web_origins=tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip()),
        )

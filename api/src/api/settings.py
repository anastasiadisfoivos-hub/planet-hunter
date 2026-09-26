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
    # Requests per minute per client IP; each bucket allows this many in a burst, then refills.
    rate_read_per_min: int = 120
    # How many proxies in front of the API append to X-Forwarded-For (Render: 1). 0 = ignore it.
    trusted_proxy_hops: int = 0
    web_origins: tuple[str, ...] = field(default_factory=tuple)
    # Planet finder
    rate_vote_per_min: int = 20
    rate_admin_per_min: int = 6
    finder_votes_needed: int = 5  # needs_votes: open candidates with fewer votes than this
    # Admin endpoints are off (404) unless set. Kept out of repr.
    admin_token: str | None = field(default=None, repr=False)
    # Monitor
    # POST /monitor/progress (the sweep's shards) is off (404) unless set. Kept out of repr.
    ingest_token: str | None = field(default=None, repr=False)
    rate_ingest_per_min: int = 600
    monitor_live_timeout_s: float = 900.0  # "live" until a running sweep is silent this long
    monitor_step_s: float = 20.0  # replay: seconds per star
    monitor_keep_runs: int = 3  # finished runs whose stars (light curves) are kept

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
            rate_read_per_min=_int("PH_RATE_READ_PER_MIN", 120),
            trusted_proxy_hops=_int("PH_TRUSTED_PROXY_HOPS", 0),
            web_origins=tuple(o.strip().rstrip("/") for o in origins.split(",") if o.strip()),
            rate_vote_per_min=_int("PH_RATE_VOTE_PER_MIN", 20),
            rate_admin_per_min=_int("PH_RATE_ADMIN_PER_MIN", 6),
            finder_votes_needed=_int("PH_FINDER_VOTES_NEEDED", 5),
            admin_token=os.environ.get("PH_ADMIN_TOKEN") or None,
            ingest_token=os.environ.get("PH_INGEST_TOKEN") or None,
            rate_ingest_per_min=_int("PH_RATE_INGEST_PER_MIN", 600),
            monitor_live_timeout_s=_float("PH_MONITOR_LIVE_TIMEOUT_S", 900.0),
            monitor_step_s=_float("PH_MONITOR_STEP_S", 20.0),
            monitor_keep_runs=_int("PH_MONITOR_KEEP_RUNS", 3),
        )

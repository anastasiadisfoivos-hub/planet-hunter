"""Choose fake or real adapters. Routes, storage and tests only ever see the ports."""

from __future__ import annotations

from dataclasses import dataclass, replace

from api.ports import KnownLists, PixelVetter, Storage
from api.settings import Settings
from api.storage.sqlite import SqliteStorage


@dataclass
class Services:
    storage: Storage
    # Only `python -m api.finder_ingest` uses these; web requests never do.
    pixel_vetter: PixelVetter | None = None
    known_lists: KnownLists | None = None


def build_storage(settings: Settings) -> Storage:
    """Postgres when PH_DATABASE_URL is set, else SQLite at PH_DB_PATH."""
    if settings.database_url:
        from api.storage.postgres import PostgresStorage

        return PostgresStorage(
            settings.database_url,
            pool_max=settings.db_pool_max,
            timeout_s=settings.db_timeout_s,
            statement_timeout_ms=settings.db_statement_timeout_ms,
        )
    return SqliteStorage(settings.db_path)


def storage_from_cli(db: str | None, database_url: str | None) -> Storage:
    """For the CLIs: --database-url, else --db, else the environment."""
    settings = Settings.from_env()
    if database_url:
        settings = replace(settings, database_url=database_url)
    elif db:
        settings = replace(settings, database_url=None, db_path=db)
    return build_storage(settings)


def build_pixel_vetter(settings: Settings) -> PixelVetter:
    """Raises ImportError under PH_ADAPTERS=real when pixels/ isn't installed."""
    if settings.adapters == "real":
        from api.adapters.finder_real import PixelsVetter

        return PixelsVetter()
    from api.fakes.finder import FakePixelVetter

    return FakePixelVetter()


def build_known_lists(settings: Settings) -> KnownLists:
    if settings.adapters == "real":
        from api.adapters.finder_real import HunterKnownLists

        return HunterKnownLists()
    from api.fakes.finder import FakeKnownLists

    return FakeKnownLists()


def build_services(settings: Settings) -> Services:
    if settings.adapters not in ("fake", "real"):
        raise ValueError(f"PH_ADAPTERS must be 'fake' or 'real', got {settings.adapters!r}")
    return Services(storage=build_storage(settings))

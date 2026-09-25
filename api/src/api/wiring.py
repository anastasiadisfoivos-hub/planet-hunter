"""Choose fake or real adapters. Routes, storage and tests only ever see the ports."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from api.ports import PlanetArchive, StarAnalyzer, Storage
from api.settings import Settings
from api.spectra_index import SpectraIndex
from api.storage.sqlite import SqliteStorage


@dataclass
class Services:
    storage: Storage
    analyzer: StarAnalyzer
    archive: PlanetArchive | None = None  # None: the lab lists no known planets
    spectra: SpectraIndex = field(default_factory=lambda: SpectraIndex(None))


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


def build_analyzer(settings: Settings) -> StarAnalyzer:
    if settings.adapters == "real":
        from api.adapters.real import PipelineAnalyzer

        return PipelineAnalyzer()
    if settings.adapters != "fake":
        raise ValueError(f"PH_ADAPTERS must be 'fake' or 'real', got {settings.adapters!r}")
    from api.fakes.tess import FakeAnalyzer

    return FakeAnalyzer()


def build_archive(settings: Settings) -> PlanetArchive:
    if settings.adapters == "real":
        from api.adapters.exoarchive import ExoplanetArchive

        return ExoplanetArchive()
    from api.fakes.archive import FakeArchive

    return FakeArchive()


def build_services(settings: Settings) -> Services:
    return Services(
        storage=build_storage(settings),
        analyzer=build_analyzer(settings),
        archive=build_archive(settings),
        spectra=SpectraIndex(settings.spectra_index, settings.spectra_index_ttl_s),
    )

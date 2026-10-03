"""python -m api.migrate: applies pending migrations and is idempotent."""

from __future__ import annotations

import pytest

from api import migrate
from api.storage import postgres, sqlite
from tests.conftest import BACKENDS


def test_migrate_sqlite(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("PH_DATABASE_URL", raising=False)
    db = tmp_path / "m.db"
    assert migrate.main(["--db", str(db)]) == 0
    assert f"{len(sqlite.migration_files())} migrations recorded" in capsys.readouterr().out
    assert migrate.main(["--db", str(db)]) == 0  # again: nothing to do


@pytest.mark.skipif("postgres" not in BACKENDS, reason="PH_TEST_BACKENDS excludes postgres")
def test_migrate_postgres(pg_url, capsys):
    # pg_url starts from an empty database; the session's pg_storage may have migrated it already.
    assert migrate.main(["--database-url", pg_url]) == 0
    assert f"{len(postgres.migration_files())} migrations recorded" in capsys.readouterr().out
    assert migrate.main(["--database-url", pg_url]) == 0
    assert "applied nothing new" in capsys.readouterr().out

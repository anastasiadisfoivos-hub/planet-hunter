"""Apply pending database migrations, then exit: python -m api.migrate [--database-url URL]

The API and `api.finder_ingest` also migrate on startup (under an advisory lock on Postgres), so
this is optional. Running it before a deploy keeps a schema error out of the web service's boot
and shows which migrations were applied.
"""

from __future__ import annotations

import argparse
import sys

from api.settings import Settings


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m api.migrate", description=__doc__.split("\n")[0])
    p.add_argument("--database-url", help="Postgres URL (default: PH_DATABASE_URL)")
    p.add_argument("--db", help="SQLite file, when there is no Postgres URL (default: PH_DB_PATH)")
    args = p.parse_args(argv)
    settings = Settings.from_env()
    url = args.database_url or (None if args.db else settings.database_url)

    if url:
        import psycopg

        from api.storage.postgres import migrate

        with psycopg.connect(url, prepare_threshold=None, connect_timeout=10) as conn:
            applied = migrate(conn)
            (count,) = conn.execute("SELECT count(*) FROM schema_migrations").fetchone()
        where = "postgres"
    else:
        from api.storage.sqlite import SqliteStorage

        path = args.db or settings.db_path
        storage = SqliteStorage(path)  # migrates on open
        try:
            applied = []  # SqliteStorage already applied them; report what is recorded
            count = len(storage._all("SELECT version FROM schema_migrations"))
        finally:
            storage.close()
        where = f"sqlite {path}"

    print(f"{where}: applied {', '.join(applied) if applied else 'nothing new'};"
          f" {count} migrations recorded")  # fmt: skip
    return 0


if __name__ == "__main__":
    sys.exit(main())

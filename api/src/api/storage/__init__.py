from api.storage.sqlite import SqliteStorage

__all__ = ["SqliteStorage", "PostgresStorage"]


def __getattr__(name: str):
    # Imported lazily so SQLite-only runs never load the Postgres driver.
    if name == "PostgresStorage":
        from api.storage.postgres import PostgresStorage

        return PostgresStorage
    raise AttributeError(name)

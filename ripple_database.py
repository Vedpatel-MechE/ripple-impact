"""Small database compatibility layer for local SQLite and hosted Postgres.

The application keeps SQLite for zero-setup local development and tests.  A
Vercel deployment supplies ``DATABASE_URL`` and uses psycopg against a managed
Postgres database.  The adapter deliberately exposes only the tiny DB-API
surface used by RIPPLE so the product logic remains shared between both modes.
"""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any, Iterator


POSTGRES_PREFIXES = ("postgres://", "postgresql://")


def is_postgres_target(target: object) -> bool:
    return isinstance(target, str) and target.startswith(POSTGRES_PREFIXES)


class HybridRow(dict):
    """A mapping that also supports SQLite-style positional access."""

    def __getitem__(self, key: object) -> Any:
        if isinstance(key, int):
            return tuple(self.values())[key]
        return super().__getitem__(key)


class PostgresCursor:
    def __init__(self, cursor: Any):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    def fetchone(self) -> HybridRow | None:
        row = self._cursor.fetchone()
        return HybridRow(row) if row is not None else None

    def fetchall(self) -> list[HybridRow]:
        return [HybridRow(row) for row in self._cursor.fetchall()]

    def __iter__(self) -> Iterator[HybridRow]:
        for row in self._cursor:
            yield HybridRow(row)


class PostgresConnection:
    backend = "postgres"

    def __init__(self, connection: Any):
        self._connection = connection

    def __enter__(self) -> "PostgresConnection":
        self._connection.__enter__()
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> object:
        return self._connection.__exit__(exc_type, exc, traceback)

    @staticmethod
    def _query(sql: str) -> str:
        if sql.strip().upper() == "BEGIN IMMEDIATE":
            return "BEGIN"
        return sql.replace("?", "%s")

    def execute(self, sql: str, parameters: tuple | list | None = None) -> PostgresCursor:
        try:
            cursor = self._connection.execute(self._query(sql), parameters or ())
        except Exception as error:
            # Preserve the exception contract used by the existing application.
            try:
                from psycopg import IntegrityError as PsycopgIntegrityError
            except ImportError:  # pragma: no cover - psycopg exists in hosted mode
                PsycopgIntegrityError = ()
            if isinstance(error, PsycopgIntegrityError):
                raise sqlite3.IntegrityError(str(error)) from error
            raise
        return PostgresCursor(cursor)

    def executescript(self, sql: str) -> None:
        # psycopg uses the simple-query protocol for an unparameterized script.
        self._connection.execute(sql, prepare=False)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def connect(target: Path | str):
    if is_postgres_target(target):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:  # pragma: no cover - local mode needs no dependency
            raise RuntimeError("Postgres mode requires psycopg[binary]") from error
        connection = psycopg.connect(
            target,
            row_factory=dict_row,
            connect_timeout=10,
            application_name="ripple-vercel",
        )
        return PostgresConnection(connection)

    db_path = Path(target)
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    return connection


def backend_name(connection: object) -> str:
    return getattr(connection, "backend", "sqlite")

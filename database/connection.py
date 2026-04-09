"""Database connection management."""

import logging
import os
import sqlite3
from contextlib import contextmanager
from typing import Any, Iterable, Optional, Sequence

import config

logger = logging.getLogger(__name__)

# Database path
DB_PATH = os.path.join(config.DATA_DIR, "yattee.db")


def _is_postgres_url(url: str) -> bool:
    return url.startswith("postgresql://") or url.startswith("postgres://")


def get_database_url() -> str:
    """Get effective database URL.

    DATABASE_URL takes precedence; otherwise defaults to local SQLite file DB.
    """
    if config.DATABASE_URL:
        return config.DATABASE_URL
    return f"sqlite:///{get_db_path()}"


def get_sqlalchemy_database_url() -> str:
    """Get database URL normalized for SQLAlchemy engine creation.

    SQLAlchemy defaults `postgresql://` to the psycopg2 driver. This project
    uses psycopg3, so plain PostgreSQL URLs are upgraded to
    `postgresql+psycopg://` automatically.
    """
    url = get_database_url()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


def is_postgres() -> bool:
    """Return True when configured to use PostgreSQL."""
    return _is_postgres_url(get_database_url())


def get_db_path() -> str:
    """Get the database file path, ensuring data directory exists."""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    return DB_PATH


def _convert_qmark_to_pyformat(sql: str) -> str:
    """Convert SQLite-style '?' placeholders to psycopg '%s'.

    Existing repositories are written with qmark placeholders. For PostgreSQL,
    translate only placeholders outside of quoted strings.
    """
    out = []
    in_single = False
    in_double = False
    i = 0
    while i < len(sql):
        ch = sql[i]
        if ch == "'" and not in_double:
            # Handle escaped single quote '' inside string literals.
            if in_single and i + 1 < len(sql) and sql[i + 1] == "'":
                out.append("''")
                i += 2
                continue
            in_single = not in_single
            out.append(ch)
        elif ch == '"' and not in_single:
            in_double = not in_double
            out.append(ch)
        elif ch == "?" and not in_single and not in_double:
            out.append("%s")
        else:
            out.append(ch)
        i += 1
    return "".join(out)


class CursorWrapper:
    """DB-API cursor wrapper that normalizes SQL placeholders across backends."""

    def __init__(self, cursor: Any, backend: str):
        self._cursor = cursor
        self._backend = backend

    def execute(self, sql: str, params: Optional[Sequence[Any]] = None):
        query = _convert_qmark_to_pyformat(sql) if self._backend == "postgres" else sql
        if params is None:
            self._cursor.execute(query)
        else:
            self._cursor.execute(query, params)
        return self

    def executemany(self, sql: str, seq_of_params: Iterable[Sequence[Any]]):
        query = _convert_qmark_to_pyformat(sql) if self._backend == "postgres" else sql
        self._cursor.executemany(query, seq_of_params)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> Any:
        return getattr(self._cursor, "lastrowid", None)

    def __getattr__(self, name: str):
        return getattr(self._cursor, name)


class ConnectionWrapper:
    """DB-API connection wrapper exposing a normalized cursor wrapper."""

    def __init__(self, conn: Any, backend: str):
        self._conn = conn
        self._backend = backend

    def cursor(self):
        return CursorWrapper(self._conn.cursor(), self._backend)

    def commit(self):
        return self._conn.commit()

    def rollback(self):
        return self._conn.rollback()

    def close(self):
        return self._conn.close()

    def __getattr__(self, name: str):
        return getattr(self._conn, name)


@contextmanager
def get_connection():
    """Get a database connection with row factory."""
    if is_postgres():
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "PostgreSQL support requires psycopg. Install it with: pip install psycopg[binary]"
            ) from exc

        db_url = get_database_url()
        if db_url.startswith("postgres://"):
            db_url = "postgresql://" + db_url[len("postgres://"):]

        raw_conn = psycopg.connect(db_url, row_factory=dict_row)
        conn = ConnectionWrapper(raw_conn, backend="postgres")
    else:
        raw_conn = sqlite3.connect(get_db_path())
        raw_conn.row_factory = sqlite3.Row
        conn = ConnectionWrapper(raw_conn, backend="sqlite")

    try:
        yield conn
    finally:
        conn.close()

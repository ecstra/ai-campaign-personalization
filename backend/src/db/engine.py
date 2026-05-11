import os
import logging

from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
from psycopg2 import pool, extensions
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
_POOL_MAX = int(os.getenv("DB_POOL_MAX", "20"))

class DatabaseEngine:

    _pg_pool: pool.ThreadedConnectionPool | None = None

    @classmethod
    def init_pool(cls) -> None:
        """
        Initializes the thread-safe connection pool. Call once at app startup.
        """
        if cls._pg_pool is not None:
            return

        db_uri = os.getenv("DATABASE_URI")
        if not db_uri:
            raise ValueError("DATABASE_URI environment variable is not set")

        dsn = extensions.parse_dsn(db_uri)
        dsn["keepalives"] = "1"
        dsn["keepalives_idle"] = "60"
        dsn["keepalives_interval"] = "10"
        dsn["keepalives_count"] = "5"
        cls._pg_pool = pool.ThreadedConnectionPool(_POOL_MIN, _POOL_MAX, **dsn)

    @classmethod
    def close_pool(cls) -> None:
        """
        Closes all connections in the pool. Call at app shutdown.
        """
        if cls._pg_pool is None:
            return

        cls._pg_pool.closeall()
        cls._pg_pool = None

    @classmethod
    def _validate_conn(cls, conn) -> bool:
        """Check if a pool connection is still alive."""
        try:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
            return True
        except Exception:
            return False

    @classmethod
    @contextmanager
    def get_connection(cls) -> Generator[Any, None, None]:
        """
        Context manager for database connections using the pool.
        Validates connections on checkout and discards dead ones.
        Healthy connections are returned to the pool; dead ones are closed permanently.
        """
        if cls._pg_pool is None:
            raise RuntimeError("Connection pool not initialized. Call init_pool() first.")

        conn = None
        ok = False
        for attempt in range(3):
            try:
                conn = cls._pg_pool.getconn()
                if not cls._validate_conn(conn):
                    logger.warning("Pool connection is dead; discarding and retrying (attempt %d)", attempt + 1)
                    cls._pg_pool.putconn(conn, close=True)
                    conn = None
                    continue
                break
            except Exception:
                if conn:
                    cls._pg_pool.putconn(conn, close=True)
                    conn = None
                if attempt == 2:
                    raise
        else:
            raise RuntimeError("Could not obtain a healthy database connection after 3 attempts")

        try:
            yield conn
            ok = True
        except Exception:
            raise
        finally:
            if conn:
                cls._pg_pool.putconn(conn, close=not ok)

    @classmethod
    @contextmanager
    def get_cursor(
        cls,
        commit: bool = False,
    ) -> Generator[Any, None, None]:
        """
        Context manager for database cursor with automatic commit/rollback.
        Returns a RealDictCursor for dictionary-style row access.
        """
        with cls.get_connection() as conn:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            try:
                yield cur
                if commit:
                    conn.commit()
            except Exception:
                try:
                    conn.rollback()
                except Exception:
                    logger.debug("Rollback failed — connection already closed")
                raise
            finally:
                cur.close()

    @classmethod
    def test_connection(cls) -> bool:
        """
        Tests if the database connection works.
        """
        try:
            with cls.get_cursor() as cur:
                cur.execute("SELECT 1")
                return True
        except Exception:
            logger.exception("Database connection test failed")
            return False
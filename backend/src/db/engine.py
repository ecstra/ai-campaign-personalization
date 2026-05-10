import os
import logging

from contextlib import contextmanager
from typing import Any, Generator

import psycopg2
from psycopg2 import pool
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

        cls._pg_pool = pool.ThreadedConnectionPool(_POOL_MIN, _POOL_MAX, db_uri)

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
    @contextmanager
    def get_connection(cls) -> Generator[Any, None, None]:
        """
        Context manager for database connections using the pool.
        Connections are returned to the pool after use, not closed.
        """
        if cls._pg_pool is None:
            raise RuntimeError("Connection pool not initialized. Call init_pool() first.")

        conn = None
        try:
            conn = cls._pg_pool.getconn()
            yield conn
        except psycopg2.Error:
            raise
        finally:
            if conn:
                cls._pg_pool.putconn(conn)

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
                conn.rollback()
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
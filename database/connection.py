from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Iterable, Any

DB_PATH = Path("data/imperio.db")


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection configured for transactional ERP workloads."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Atomic transaction helper with rollback on any failure."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_many(sql: str, rows: Iterable[Iterable[Any]]) -> None:
    with db_transaction() as conn:
        conn.executemany(sql, rows)

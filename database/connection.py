from __future__ import annotations

import os
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Iterable


def resolve_db_path() -> Path:
    """Resolve a writable SQLite path for local and Streamlit Cloud runs."""
    configured_path = os.getenv("IMPERIO_DB_PATH")
    if configured_path:
        return Path(configured_path).expanduser()

    repo_default = Path("data/imperio.db")
    try:
        repo_default.parent.mkdir(parents=True, exist_ok=True)
        with open(repo_default.parent / ".write_test", "a", encoding="utf-8"):
            pass
        (repo_default.parent / ".write_test").unlink(missing_ok=True)
        return repo_default
    except OSError:
        temp_dir = Path(tempfile.gettempdir()) / "imperio-atomico"
        temp_dir.mkdir(parents=True, exist_ok=True)
        return temp_dir / "imperio.db"


DB_PATH = resolve_db_path()


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

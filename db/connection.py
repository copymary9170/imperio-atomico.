from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional

from config import DATABASE


def get_db_path() -> str:
    return DATABASE if str(DATABASE or "").strip() else "database.db"


def configure_connection(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    conn.execute("PRAGMA cache_size = -10000;")
    conn.execute("PRAGMA busy_timeout = 30000;")
    return conn


def connect(path: Optional[str] = None) -> sqlite3.Connection:
    conn = sqlite3.connect(
        path or get_db_path(),
        timeout=30,
        isolation_level=None,
        detect_types=sqlite3.PARSE_DECLTYPES,
    )
    return configure_connection(conn)


@contextmanager
def db_session(path: Optional[str] = None) -> Iterator[sqlite3.Connection]:
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
services/__init__.py
services/__init__.py
Nuevo
+1
-0

Diferencia grande
1 líneas

Cargar diferencia
services/diagnostics_service.py
services/diagnostics_service.py
Nuevo
+48
-0

Diferencia grande
48 líneas

Cargar diferencia

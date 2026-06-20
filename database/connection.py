from __future__ import annotations

import os
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Generator


_CORRUPT_HANDLED = False


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


def _quarantine_bad_database(reason: str = "corrupta") -> None:
    """Aparta una base dañada para que SQLite no intente abrirla otra vez."""
    if not DB_PATH.exists():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = DB_PATH.with_name(f"{DB_PATH.stem}_{reason}_{stamp}{DB_PATH.suffix}")
    try:
        shutil.move(str(DB_PATH), str(target))
    except Exception:
        try:
            DB_PATH.unlink(missing_ok=True)
        except Exception:
            pass


def _try_remote_recovery() -> None:
    """Intenta traer el último respaldo de GitHub antes de crear una base vacía."""
    try:
        from services.backup_service import restore_remote_database_if_needed

        restore_remote_database_if_needed(force=True)
    except Exception:
        pass


def _open_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection configured for transactional ERP workloads.

    Si Streamlit arranca con un archivo imperio.db vacío o dañado, SQLite puede
    fallar incluso antes de crear las tablas. En ese caso apartamos el archivo,
    intentamos restaurar el último respaldo remoto y volvemos a abrir la base.
    """
    global _CORRUPT_HANDLED
    try:
        return _open_connection()
    except sqlite3.DatabaseError:
        if _CORRUPT_HANDLED:
            raise
        _CORRUPT_HANDLED = True
        _quarantine_bad_database("corrupta")
        _try_remote_recovery()
        return _open_connection()


@contextmanager
def db_transaction() -> Generator[sqlite3.Connection, None, None]:
    """Atomic transaction helper with rollback and remote persistence after writes."""
    conn = get_connection()
    changed = False
    try:
        before = conn.total_changes
        yield conn
        conn.commit()
        changed = conn.total_changes > before
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    if changed and os.getenv("IMPERIO_DISABLE_AUTO_PERSIST", "0") != "1":
        try:
            from services.backup_service import persist_database_snapshot

            persist_database_snapshot("auto_cambio")
        except Exception:
            # El cambio local ya fue confirmado. El estado del respaldo se mostrará
            # en la pantalla de Respaldo para que el usuario pueda reintentarlo.
            pass

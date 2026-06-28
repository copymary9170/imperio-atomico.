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
_RECOVERY_CHECKED = False

BUSINESS_TABLES = (
    "usuarios",
    "inventario",
    "clientes",
    "proveedores",
    "ventas",
    "cotizaciones",
    "facturas_compra",
    "movimientos_inventario",
    "kardex",
)


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


def _local_has_business_data() -> bool:
    if not DB_PATH.exists() or DB_PATH.stat().st_size < 100:
        return False
    try:
        with sqlite3.connect(str(DB_PATH)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            for table in BUSINESS_TABLES:
                if table not in tables:
                    continue
                total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                if int(total or 0) > 0:
                    return True
    except Exception:
        return False
    return False


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


def _try_remote_recovery(force: bool = True) -> None:
    """Intenta traer el mejor respaldo remoto antes de crear una base vacía."""
    try:
        from services.backup_recovery_service import restore_best_remote_backup

        restore_best_remote_backup(force=force)
    except Exception:
        try:
            from services.backup_service import restore_remote_database_if_needed

            restore_remote_database_if_needed(force=force)
        except Exception:
            pass


def _restore_if_local_empty() -> None:
    global _RECOVERY_CHECKED
    if _RECOVERY_CHECKED:
        return
    _RECOVERY_CHECKED = True
    if _local_has_business_data():
        return
    _try_remote_recovery(force=True)


def _open_connection() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    return conn


def get_connection() -> sqlite3.Connection:
    """Create a SQLite connection configured for transactional ERP workloads."""
    global _CORRUPT_HANDLED
    _restore_if_local_empty()
    try:
        return _open_connection()
    except sqlite3.DatabaseError:
        if _CORRUPT_HANDLED:
            raise
        _CORRUPT_HANDLED = True
        _quarantine_bad_database("corrupta")
        _try_remote_recovery(force=True)
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
            pass

from __future__ import annotations

import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = APP_ROOT / "data"
BACKUP_DIR = DATA_DIR / "backups"
BACKUP_META = BACKUP_DIR / "backup_meta.json"

DB_CANDIDATES = [
    DATA_DIR / "imperio_atomico.db",
    DATA_DIR / "app.db",
    DATA_DIR / "database.db",
    APP_ROOT / "imperio_atomico.db",
    APP_ROOT / "data.db",
]


def get_database_path() -> Path | None:
    for path in DB_CANDIDATES:
        if path.exists():
            return path
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        found = sorted(DATA_DIR.glob(pattern)) if DATA_DIR.exists() else []
        if found:
            return found[0]
    return None


def ensure_backup_dir() -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)


def _read_meta() -> dict:
    try:
        if BACKUP_META.exists():
            return json.loads(BACKUP_META.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_meta(meta: dict) -> None:
    ensure_backup_dir()
    BACKUP_META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def create_backup(reason: str = "manual") -> Path | None:
    ensure_backup_dir()
    db_path = get_database_path()
    if not db_path or not db_path.exists():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"imperio_atomico_{reason}_{stamp}.db"
    try:
        src = sqlite3.connect(str(db_path))
        dst = sqlite3.connect(str(backup_path))
        with dst:
            src.backup(dst)
        src.close()
        dst.close()
    except Exception:
        shutil.copy2(db_path, backup_path)
    meta = _read_meta()
    meta["last_backup_at"] = datetime.now().isoformat(timespec="seconds")
    meta["last_backup_reason"] = reason
    meta["last_backup_file"] = backup_path.name
    meta["last_backup_day"] = datetime.now().strftime("%Y-%m-%d")
    _write_meta(meta)
    prune_backups(keep=20)
    return backup_path


def create_daily_backup_if_needed() -> Path | None:
    meta = _read_meta()
    today = datetime.now().strftime("%Y-%m-%d")
    if meta.get("last_backup_day") == today:
        return None
    return create_backup("auto_diario")


def list_backups() -> list[Path]:
    ensure_backup_dir()
    return sorted(BACKUP_DIR.glob("*.db"), key=lambda p: p.stat().st_mtime, reverse=True)


def prune_backups(keep: int = 20) -> None:
    backups = list_backups()
    for old in backups[int(keep):]:
        try:
            old.unlink()
        except Exception:
            pass


def restore_backup(uploaded_file) -> bool:
    db_path = get_database_path()
    if db_path is None:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        db_path = DATA_DIR / "imperio_atomico.db"
    create_backup("antes_restaurar")
    try:
        db_path.write_bytes(uploaded_file.getvalue())
        meta = _read_meta()
        meta["last_restore_at"] = datetime.now().isoformat(timespec="seconds")
        meta["last_restore_file"] = getattr(uploaded_file, "name", "respaldo_subido.db")
        _write_meta(meta)
        return True
    except Exception:
        return False


def get_backup_status() -> dict:
    db_path = get_database_path()
    meta = _read_meta()
    backups = list_backups()
    return {
        "db_path": str(db_path) if db_path else "No detectada",
        "db_exists": bool(db_path and db_path.exists()),
        "backup_dir": str(BACKUP_DIR),
        "total_backups": len(backups),
        "last_backup_at": meta.get("last_backup_at", "Nunca"),
        "last_backup_reason": meta.get("last_backup_reason", ""),
        "last_backup_file": meta.get("last_backup_file", ""),
        "last_restore_at": meta.get("last_restore_at", "Nunca"),
    }

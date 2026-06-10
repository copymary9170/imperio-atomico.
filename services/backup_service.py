from __future__ import annotations

import base64
import hashlib
import hmac
import json
import shutil
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

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


def _secret(name: str, default: str = "") -> str:
    try:
        if st is not None and name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    return default


def _xor_protect(data: bytes, password: str) -> bytes:
    if not password:
        return data
    key = hashlib.sha256(password.encode("utf-8")).digest()
    return bytes(byte ^ key[i % len(key)] for i, byte in enumerate(data))


def _protected_payload(path: Path, password: str) -> bytes:
    raw = path.read_bytes()
    salt = datetime.now().strftime("%Y%m%d%H%M%S").encode("utf-8")
    signature = hmac.new(password.encode("utf-8"), raw, hashlib.sha256).hexdigest().encode("utf-8") if password else b""
    encrypted = _xor_protect(raw, password)
    envelope = {
        "format": "copy-mary-backup-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "original_name": path.name,
        "note": "Respaldo protegido. Restaurar desde el ERP con BACKUP_PASSWORD.",
        "salt": salt.decode("utf-8"),
        "signature_sha256_hmac": signature.decode("utf-8") if signature else "",
        "payload_base64": base64.b64encode(encrypted).decode("ascii"),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def _github_upload_bytes(content: bytes, repo: str, token: str, remote_path: str, message: str) -> tuple[bool, str]:
    owner_repo = repo.strip().strip("/")
    if "/" not in owner_repo:
        return False, "Repositorio inválido."
    api_url = f"https://api.github.com/repos/{owner_repo}/contents/{remote_path}"
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
    }
    req = urllib.request.Request(
        api_url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            if 200 <= resp.status < 300:
                return True, remote_path
            return False, f"GitHub respondió estado {resp.status}."
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:
            detail = str(exc)
        return False, f"Error GitHub {exc.code}: {detail}"
    except Exception as exc:
        return False, str(exc)


def upload_backup_to_github(backup_path: Path) -> tuple[bool, str]:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    password = _secret("BACKUP_PASSWORD")
    if not token or not repo:
        return False, "Faltan GITHUB_TOKEN o GITHUB_REPO en Secrets."
    protected = _protected_payload(backup_path, password)
    remote_name = backup_path.with_suffix(".protected.json").name
    remote_path = f"backups/{datetime.now().strftime('%Y/%m')}/{remote_name}"
    return _github_upload_bytes(
        protected,
        repo,
        token,
        remote_path,
        f"Respaldo automatico {backup_path.name}",
    )


def create_backup(reason: str = "manual", upload_external: bool = True) -> Path | None:
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

    if upload_external:
        ok, message = upload_backup_to_github(backup_path)
        meta["last_external_backup_ok"] = ok
        meta["last_external_backup_message"] = message
        meta["last_external_backup_at"] = datetime.now().isoformat(timespec="seconds")

    _write_meta(meta)
    prune_backups(keep=20)
    return backup_path


def create_daily_backup_if_needed() -> Path | None:
    meta = _read_meta()
    today = datetime.now().strftime("%Y-%m-%d")
    if meta.get("last_backup_day") == today:
        return None
    return create_backup("auto_diario", upload_external=True)


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
    create_backup("antes_restaurar", upload_external=True)
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
        "last_external_backup_ok": meta.get("last_external_backup_ok", False),
        "last_external_backup_message": meta.get("last_external_backup_message", "Sin respaldo externo todavía"),
        "last_external_backup_at": meta.get("last_external_backup_at", "Nunca"),
        "github_configured": bool(_secret("GITHUB_TOKEN") and _secret("GITHUB_REPO")),
    }

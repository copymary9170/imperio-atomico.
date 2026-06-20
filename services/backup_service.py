from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import shutil
import sqlite3
import urllib.error
import urllib.parse
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
REMOTE_LATEST_PATH = "backups/latest.protected.json"
DEFAULT_BACKUP_BRANCH = "data-backups"
BUSINESS_TABLES = (
    "inventario",
    "clientes",
    "proveedores",
    "ventas",
    "cotizaciones",
    "facturas_compra",
    "movimientos_inventario",
    "kardex",
)

DB_CANDIDATES = [
    DATA_DIR / "imperio.db",
    DATA_DIR / "imperio_atomico.db",
    DATA_DIR / "app.db",
    DATA_DIR / "database.db",
    APP_ROOT / "imperio_atomico.db",
    APP_ROOT / "data.db",
]


def _runtime_db_path() -> Path | None:
    try:
        from database.connection import DB_PATH

        return Path(DB_PATH)
    except Exception:
        return None


def get_database_path() -> Path | None:
    runtime_path = _runtime_db_path()
    if runtime_path and runtime_path.exists():
        return runtime_path
    configured = os.getenv("IMPERIO_DB_PATH")
    if configured:
        configured_path = Path(configured).expanduser()
        if configured_path.exists():
            return configured_path
    for path in DB_CANDIDATES:
        if path.exists():
            return path
    for pattern in ("*.db", "*.sqlite", "*.sqlite3"):
        found = sorted(DATA_DIR.glob(pattern)) if DATA_DIR.exists() else []
        if found:
            return found[0]
    return None


def get_target_database_path() -> Path:
    runtime_path = _runtime_db_path()
    if runtime_path:
        return runtime_path
    configured = os.getenv("IMPERIO_DB_PATH")
    if configured:
        return Path(configured).expanduser()
    return DATA_DIR / "imperio.db"


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
    return os.getenv(name, default).strip()


def _xor_protect(data: bytes, password: str) -> bytes:
    if not password:
        return data
    key = hashlib.sha256(password.encode("utf-8")).digest()
    return bytes(byte ^ key[i % len(key)] for i, byte in enumerate(data))


def _build_protected_payload(raw: bytes, original_name: str, password: str) -> bytes:
    signature = hmac.new(password.encode("utf-8"), raw, hashlib.sha256).hexdigest() if password else ""
    envelope = {
        "format": "copy-mary-backup-v1",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "original_name": original_name,
        "note": "Respaldo protegido. Restaurar desde el ERP con BACKUP_PASSWORD.",
        "signature_sha256_hmac": signature,
        "payload_base64": base64.b64encode(_xor_protect(raw, password)).decode("ascii"),
    }
    return json.dumps(envelope, ensure_ascii=False, indent=2).encode("utf-8")


def _protected_payload(path: Path, password: str) -> bytes:
    return _build_protected_payload(path.read_bytes(), path.name, password)


def _decode_protected_payload(payload: bytes, password: str) -> bytes:
    envelope = json.loads(payload.decode("utf-8"))
    if envelope.get("format") != "copy-mary-backup-v1":
        raise ValueError("Formato de respaldo no reconocido.")
    encrypted = base64.b64decode(envelope.get("payload_base64", ""))
    raw = _xor_protect(encrypted, password)
    expected = str(envelope.get("signature_sha256_hmac", ""))
    actual = hmac.new(password.encode("utf-8"), raw, hashlib.sha256).hexdigest() if password else ""
    if expected and not hmac.compare_digest(expected, actual):
        raise ValueError("La contraseña del respaldo no coincide.")
    if not raw.startswith(b"SQLite format 3"):
        raise ValueError("El respaldo no contiene una base SQLite válida.")
    return raw


def _sqlite_tables(path: Path) -> set[str]:
    if not path.exists() or path.stat().st_size < 100:
        return set()
    try:
        with sqlite3.connect(str(path)) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        return {str(row[0]) for row in rows}
    except Exception:
        return set()


def database_has_business_data(path: Path | None = None) -> bool:
    db_path = path or get_database_path()
    if not db_path or not db_path.exists() or db_path.stat().st_size < 100:
        return False
    tables = _sqlite_tables(db_path)
    try:
        with sqlite3.connect(str(db_path)) as conn:
            for table in BUSINESS_TABLES:
                if table not in tables:
                    continue
                total = conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                if int(total or 0) > 0:
                    return True
    except Exception:
        return False
    return False


def _github_request(url: str, token: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, bytes]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return int(resp.status), resp.read()
    except urllib.error.HTTPError as exc:
        return int(exc.code), exc.read()


def _ensure_backup_branch(repo: str, token: str, branch: str) -> tuple[bool, str]:
    base = f"https://api.github.com/repos/{repo}"
    status, _body = _github_request(f"{base}/git/ref/heads/{urllib.parse.quote(branch, safe='')}", token)
    if status == 200:
        return True, branch
    status, body = _github_request(base, token)
    if status != 200:
        return False, "No se pudo consultar el repositorio."
    repo_info = json.loads(body.decode("utf-8"))
    default_branch = repo_info.get("default_branch", "main")
    status, body = _github_request(f"{base}/git/ref/heads/{urllib.parse.quote(default_branch, safe='')}", token)
    if status != 200:
        return False, "No se pudo consultar la rama principal."
    sha = json.loads(body.decode("utf-8"))["object"]["sha"]
    status, _body = _github_request(
        f"{base}/git/refs",
        token,
        method="POST",
        payload={"ref": f"refs/heads/{branch}", "sha": sha},
    )
    if status in (200, 201, 422):
        return True, branch
    return False, f"No se pudo crear la rama de respaldos: {status}."


def _github_put_content(content: bytes, repo: str, token: str, remote_path: str, message: str, branch: str) -> tuple[bool, str]:
    owner_repo = repo.strip().strip("/")
    if "/" not in owner_repo:
        return False, "Repositorio inválido."
    ok, detail = _ensure_backup_branch(owner_repo, token, branch)
    if not ok:
        return False, detail
    api_url = f"https://api.github.com/repos/{owner_repo}/contents/{remote_path}"
    query_url = f"{api_url}?ref={urllib.parse.quote(branch, safe='')}"
    status, body = _github_request(query_url, token)
    existing_sha = None
    if status == 200:
        existing_sha = json.loads(body.decode("utf-8")).get("sha")
    payload = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    if existing_sha:
        payload["sha"] = existing_sha
    status, body = _github_request(api_url, token, method="PUT", payload=payload)
    if status in (200, 201):
        return True, f"{branch}:{remote_path}"
    try:
        detail = json.loads(body.decode("utf-8")).get("message", body.decode("utf-8")[:300])
    except Exception:
        detail = body.decode("utf-8", errors="ignore")[:300]
    return False, f"Error GitHub {status}: {detail}"


def _github_get_content(repo: str, token: str, remote_path: str, branch: str) -> bytes | None:
    api_url = f"https://api.github.com/repos/{repo}/contents/{remote_path}?ref={urllib.parse.quote(branch, safe='')}"
    status, body = _github_request(api_url, token)
    if status != 200:
        return None
    info = json.loads(body.decode("utf-8"))
    encoded = str(info.get("content", "")).replace("\n", "")
    return base64.b64decode(encoded) if encoded else None


def _remote_latest_exists() -> bool:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    branch = _secret("BACKUP_BRANCH", DEFAULT_BACKUP_BRANCH)
    if not token or not repo:
        return False
    return _github_get_content(repo, token, REMOTE_LATEST_PATH, branch) is not None


def upload_backup_to_github(backup_path: Path, *, archive: bool = True) -> tuple[bool, str]:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    password = _secret("BACKUP_PASSWORD")
    branch = _secret("BACKUP_BRANCH", DEFAULT_BACKUP_BRANCH)
    if not token or not repo:
        return False, "Faltan GITHUB_TOKEN o GITHUB_REPO en Secrets."
    if not password:
        return False, "Falta BACKUP_PASSWORD en Secrets."
    protected = _protected_payload(backup_path, password)
    ok, message = _github_put_content(
        protected,
        repo,
        token,
        REMOTE_LATEST_PATH,
        f"Actualizar respaldo persistente {backup_path.name}",
        branch,
    )
    if not ok:
        return False, message
    if archive:
        remote_name = backup_path.with_suffix(".protected.json").name
        archive_path = f"backups/{datetime.now().strftime('%Y/%m')}/{remote_name}"
        archive_ok, archive_message = _github_put_content(
            protected,
            repo,
            token,
            archive_path,
            f"Archivar respaldo {backup_path.name}",
            branch,
        )
        if not archive_ok:
            return False, archive_message
    return True, message


def create_backup(reason: str = "manual", upload_external: bool = True, *, archive: bool = True) -> Path | None:
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

    external_allowed = upload_external
    if upload_external and reason in {"auto_cambio", "auto_diario"} and not database_has_business_data(backup_path):
        if _remote_latest_exists():
            external_allowed = False
            meta["last_external_backup_ok"] = False
            meta["last_external_backup_message"] = "Respaldo remoto protegido: la base local no tiene datos de negocio."
            meta["last_external_backup_at"] = datetime.now().isoformat(timespec="seconds")

    if external_allowed:
        ok, message = upload_backup_to_github(backup_path, archive=archive)
        meta["last_external_backup_ok"] = ok
        meta["last_external_backup_message"] = message
        meta["last_external_backup_at"] = datetime.now().isoformat(timespec="seconds")
    _write_meta(meta)
    prune_backups(keep=20)
    return backup_path


def persist_database_snapshot(reason: str = "auto_cambio") -> tuple[bool, str]:
    backup = create_backup(reason, upload_external=True, archive=False)
    if not backup:
        return False, "No se detectó la base de datos."
    meta = _read_meta()
    return bool(meta.get("last_external_backup_ok")), str(meta.get("last_external_backup_message", ""))


def restore_remote_database_if_needed(force: bool = False) -> tuple[bool, str]:
    target = get_target_database_path()
    local_has_data = database_has_business_data(target)
    if target.exists() and target.stat().st_size > 100 and local_has_data and not force:
        return False, "La base local ya tiene datos."
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    password = _secret("BACKUP_PASSWORD")
    branch = _secret("BACKUP_BRANCH", DEFAULT_BACKUP_BRANCH)
    if not token or not repo or not password:
        return False, "Faltan Secrets para restauración automática."
    payload = _github_get_content(repo, token, REMOTE_LATEST_PATH, branch)
    if not payload:
        return False, "Todavía no existe un respaldo remoto persistente."
    raw = _decode_protected_payload(payload, password)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(raw)
    meta = _read_meta()
    meta["last_restore_at"] = datetime.now().isoformat(timespec="seconds")
    meta["last_restore_file"] = f"{branch}:{REMOTE_LATEST_PATH}"
    _write_meta(meta)
    return True, "Base restaurada desde el respaldo remoto."


def create_daily_backup_if_needed() -> Path | None:
    meta = _read_meta()
    today = datetime.now().strftime("%Y-%m-%d")
    if meta.get("last_backup_day") == today:
        return None
    return create_backup("auto_diario", upload_external=True, archive=True)


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
    db_path = get_target_database_path()
    create_backup("antes_restaurar", upload_external=True, archive=True)
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        db_path.write_bytes(uploaded_file.getvalue())
        meta = _read_meta()
        meta["last_restore_at"] = datetime.now().isoformat(timespec="seconds")
        meta["last_restore_file"] = getattr(uploaded_file, "name", "respaldo_subido.db")
        _write_meta(meta)
        if database_has_business_data(db_path):
            persist_database_snapshot("restaurado")
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
        "db_has_business_data": database_has_business_data(db_path),
        "backup_dir": str(BACKUP_DIR),
        "total_backups": len(backups),
        "last_backup_at": meta.get("last_backup_at", "Nunca"),
        "last_backup_reason": meta.get("last_backup_reason", ""),
        "last_backup_file": meta.get("last_backup_file", ""),
        "last_restore_at": meta.get("last_restore_at", "Nunca"),
        "last_external_backup_ok": meta.get("last_external_backup_ok", False),
        "last_external_backup_message": meta.get("last_external_backup_message", "Sin respaldo externo todavía"),
        "last_external_backup_at": meta.get("last_external_backup_at", "Nunca"),
        "github_configured": bool(_secret("GITHUB_TOKEN") and _secret("GITHUB_REPO") and _secret("BACKUP_PASSWORD")),
        "backup_branch": _secret("BACKUP_BRANCH", DEFAULT_BACKUP_BRANCH),
    }

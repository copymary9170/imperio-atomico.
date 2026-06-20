from __future__ import annotations

import base64
import json
import sqlite3
import tempfile
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from services.backup_service import (
    DEFAULT_BACKUP_BRANCH,
    REMOTE_LATEST_PATH,
    _decode_protected_payload,
    _secret,
    database_has_business_data,
    get_target_database_path,
)


def _request(url: str, token: str) -> tuple[int, bytes]:
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            return int(resp.status), resp.read()
    except Exception as exc:
        status = getattr(exc, "code", 0) or 0
        body = exc.read() if hasattr(exc, "read") else str(exc).encode("utf-8")
        return int(status), body


def _get_content(repo: str, token: str, path: str, branch: str) -> bytes | None:
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={urllib.parse.quote(branch, safe='')}"
    status, body = _request(url, token)
    if status != 200:
        return None
    info = json.loads(body.decode("utf-8"))
    encoded = str(info.get("content", "")).replace("\n", "")
    return base64.b64decode(encoded) if encoded else None


def _list_dir(repo: str, token: str, path: str, branch: str) -> list[dict]:
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={urllib.parse.quote(branch, safe='')}"
    status, body = _request(url, token)
    if status != 200:
        return []
    try:
        data = json.loads(body.decode("utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _raw_has_data(raw: bytes) -> bool:
    if not raw.startswith(b"SQLite format 3"):
        return False
    tmp_dir = Path(tempfile.gettempdir()) / "imperio-atomico-restore-check"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f"check_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.db"
    try:
        tmp_path.write_bytes(raw)
        return database_has_business_data(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _candidate_paths(repo: str, token: str, branch: str) -> list[str]:
    paths = [REMOTE_LATEST_PATH]
    years = _list_dir(repo, token, "backups", branch)
    year_dirs = [item for item in years if item.get("type") == "dir" and str(item.get("name", "")).isdigit()]
    for year in sorted(year_dirs, key=lambda item: str(item.get("name")), reverse=True):
        year_name = str(year.get("name"))
        months = _list_dir(repo, token, f"backups/{year_name}", branch)
        month_dirs = [item for item in months if item.get("type") == "dir"]
        for month in sorted(month_dirs, key=lambda item: str(item.get("name")), reverse=True):
            month_path = f"backups/{year_name}/{month.get('name')}"
            files = _list_dir(repo, token, month_path, branch)
            protected = [item for item in files if item.get("type") == "file" and str(item.get("name", "")).endswith(".protected.json")]
            protected.sort(key=lambda item: str(item.get("name")), reverse=True)
            paths.extend([f"{month_path}/{item.get('name')}" for item in protected])
    unique = []
    seen = set()
    for path in paths:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique[:100]


def restore_best_remote_backup(force: bool = False) -> tuple[bool, str]:
    target = get_target_database_path()
    if target.exists() and target.stat().st_size > 100 and database_has_business_data(target) and not force:
        return False, "La base local ya tiene datos."

    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    password = _secret("BACKUP_PASSWORD")
    branch = _secret("BACKUP_BRANCH", DEFAULT_BACKUP_BRANCH)
    if not token or not repo or not password:
        return False, "Faltan Secrets para restaurar desde GitHub."

    last_error = "No se encontró respaldo remoto con datos."
    for path in _candidate_paths(repo, token, branch):
        payload = _get_content(repo, token, path, branch)
        if not payload:
            continue
        try:
            raw = _decode_protected_payload(payload, password)
        except Exception as exc:
            last_error = f"No se pudo leer {path}: {exc}"
            continue
        if not _raw_has_data(raw):
            last_error = f"{path} no tiene datos de negocio."
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return True, f"Base restaurada desde {branch}:{path}."
    return False, last_error

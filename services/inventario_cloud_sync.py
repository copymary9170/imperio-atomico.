from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from database.connection import db_transaction

BACKUP_BRANCH = "data-backups"
REMOTE_PATH = "inventory/inventario_unificado.json"
INVENTARIO_FIELDS = [
    "usuario", "sku", "nombre", "categoria", "unidad", "unidad_base", "tipo_uso",
    "permite_fraccionamiento", "stock_actual", "stock_minimo", "costo_unitario_usd",
    "precio_venta_usd", "marca", "color", "tamano", "gramaje", "acabado",
    "ancho_cm", "alto_cm", "margen_izquierdo_cm", "margen_derecho_cm",
    "margen_superior_cm", "margen_inferior_cm", "separacion_cm", "sangrado_cm",
    "merma_base_pct", "unidad_compra", "contenido_compra", "proveedor_principal",
    "ubicacion", "stock_ideal", "stock_maximo", "punto_reorden", "observaciones", "estado",
]


def _secret(name: str, default: str = "") -> str:
    try:
        if st is not None and name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    return os.getenv(name, default).strip()


def _request(url: str, token: str, *, method: str = "GET", payload: dict | None = None) -> tuple[int, bytes]:
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
    except Exception as exc:
        return 0, str(exc).encode("utf-8")


def _repo_token_branch() -> tuple[str, str, str] | None:
    token = _secret("GITHUB_TOKEN")
    repo = _secret("GITHUB_REPO")
    branch = _secret("BACKUP_BRANCH", BACKUP_BRANCH)
    if not token or not repo:
        return None
    return repo.strip().strip("/"), token, branch


def _get_file_info(repo: str, token: str, branch: str) -> dict[str, Any] | None:
    url = f"https://api.github.com/repos/{repo}/contents/{REMOTE_PATH}?ref={urllib.parse.quote(branch, safe='')}"
    status, body = _request(url, token)
    if status != 200:
        return None
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return None


def _read_remote_json() -> dict[str, Any] | None:
    cfg = _repo_token_branch()
    if not cfg:
        return None
    repo, token, branch = cfg
    info = _get_file_info(repo, token, branch)
    if not info:
        return None
    encoded = str(info.get("content", "")).replace("\n", "")
    if not encoded:
        return None
    try:
        return json.loads(base64.b64decode(encoded).decode("utf-8"))
    except Exception:
        return None


def _write_remote_json(payload: dict[str, Any]) -> tuple[bool, str]:
    cfg = _repo_token_branch()
    if not cfg:
        return False, "Faltan GITHUB_TOKEN o GITHUB_REPO."
    repo, token, branch = cfg
    url = f"https://api.github.com/repos/{repo}/contents/{REMOTE_PATH}"
    content = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    last_error = ""
    for _ in range(3):
        info = _get_file_info(repo, token, branch)
        body = {
            "message": "Actualizar respaldo JSON de inventario",
            "branch": branch,
            "content": base64.b64encode(content).decode("ascii"),
        }
        if info and info.get("sha"):
            body["sha"] = info["sha"]
        status, response = _request(url, token, method="PUT", payload=body)
        if status in (200, 201):
            return True, f"{branch}:{REMOTE_PATH}"
        try:
            last_error = json.loads(response.decode("utf-8")).get("message", response.decode("utf-8")[:200])
        except Exception:
            last_error = response.decode("utf-8", errors="ignore")[:200]
        if status != 409:
            break
    return False, f"GitHub {last_error}"


def export_inventario_to_github() -> tuple[bool, str]:
    with db_transaction() as conn:
        rows = conn.execute(
            f"SELECT {', '.join(INVENTARIO_FIELDS)} FROM inventario ORDER BY id"
        ).fetchall()
        items = [{field: row[field] for field in INVENTARIO_FIELDS} for row in rows]
    if not items:
        return False, "Inventario vacío: no se subió JSON para no perder el respaldo bueno."
    payload = {
        "format": "copy-mary-inventario-json-v1",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "total_items": len(items),
        "items": items,
    }
    return _write_remote_json(payload)


def restore_inventario_from_github_if_empty(usuario: str = "Sistema") -> tuple[bool, str]:
    with db_transaction() as conn:
        current = conn.execute("SELECT COUNT(*) FROM inventario").fetchone()[0]
    if int(current or 0) > 0:
        return False, "El inventario local ya tiene artículos."
    payload = _read_remote_json()
    if not payload or payload.get("format") != "copy-mary-inventario-json-v1":
        return False, "No hay respaldo JSON de inventario en GitHub."
    items = payload.get("items") or []
    if not isinstance(items, list) or not items:
        return False, "El respaldo JSON de inventario está vacío."
    insert_sql = f"""
        INSERT OR IGNORE INTO inventario({', '.join(INVENTARIO_FIELDS)})
        VALUES ({', '.join(['?'] * len(INVENTARIO_FIELDS))})
    """
    with db_transaction() as conn:
        for item in items:
            values = [item.get(field) for field in INVENTARIO_FIELDS]
            if not values[0]:
                values[0] = usuario
            conn.execute(insert_sql, values)
    return True, f"Inventario restaurado desde GitHub: {len(items)} artículo(s)."

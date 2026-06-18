from __future__ import annotations

import base64
import json
import sqlite3
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import streamlit as st
except Exception:  # pragma: no cover
    st = None

from database.connection import db_transaction

APP_ROOT = Path(__file__).resolve().parents[1]
LOCAL_CONFIG_PATH = APP_ROOT / "data" / "persistent_rates_config.json"
REMOTE_CONFIG_PATH = "runtime/persistent_rates_config.json"

RATE_CONFIG_KEYS = [
    "tasa_bcv",
    "tasa_binance",
    "tasa_euro",
    "tasa_menudeo",
    "tasa_kontigo",
    "tasa_kontigo_entrada",
    "tasa_kontigo_salida",
    "iva_perc",
    "igtf_perc",
    "banco_perc",
    "kontigo_perc",
    "kontigo_perc_entrada",
    "kontigo_perc_salida",
    "kontigo_pago_movil_envio_perc",
    "kontigo_tarjeta_envio_perc",
    "kontigo_tarjeta_envio_fija_usd",
    "menudeo_comision_perc",
    "menudeo_comision_fija_usd",
    "menudeo_minimo_usd",
]


def _secret(name: str, default: str = "") -> str:
    try:
        if st is not None and name in st.secrets:
            return str(st.secrets.get(name, default)).strip()
    except Exception:
        pass
    return default


def _github_request(url: str, token: str, method: str = "GET", payload: dict | None = None) -> tuple[bool, dict[str, Any] | str]:
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
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return True, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return False, "404"
        try:
            return False, exc.read().decode("utf-8")[:500]
        except Exception:
            return False, str(exc)
    except Exception as exc:
        return False, str(exc)


def _github_repo_and_token() -> tuple[str, str]:
    return _secret("GITHUB_REPO"), _secret("GITHUB_TOKEN")


def _remote_url(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/contents/{REMOTE_CONFIG_PATH}"


def _normalize_payload(values: dict[str, Any]) -> dict[str, Any]:
    rates: dict[str, Any] = {}
    for key in RATE_CONFIG_KEYS:
        if key in values:
            try:
                rates[key] = float(values[key])
            except Exception:
                rates[key] = values[key]
    return {
        "format": "imperio-atomico-persistent-rates-v1",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "rates": rates,
    }


def _ensure_minimal_config_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS configuracion (
                parametro TEXT PRIMARY KEY,
                valor TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_config (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parametro TEXT NOT NULL,
                valor_anterior TEXT,
                valor_nuevo TEXT,
                usuario TEXT,
                fecha TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _upsert_rates_direct(values: dict[str, Any], usuario: str) -> None:
    """Direct DB upsert used during app boot so config defaults cannot raise IntegrityError."""
    if not values:
        return
    _ensure_minimal_config_tables()
    with db_transaction() as conn:
        for key, value in values.items():
            if key not in RATE_CONFIG_KEYS:
                continue
            new_value = str(value)
            old = conn.execute("SELECT valor FROM configuracion WHERE parametro=?", (key,)).fetchone()
            old_value = old["valor"] if old and old["valor"] is not None else None
            conn.execute(
                """
                INSERT INTO configuracion (parametro, valor)
                VALUES (?, ?)
                ON CONFLICT(parametro) DO UPDATE SET valor=excluded.valor
                """,
                (key, new_value),
            )
            if old_value != new_value:
                conn.execute(
                    """
                    INSERT INTO historial_config (parametro, valor_anterior, valor_nuevo, usuario)
                    VALUES (?, ?, ?, ?)
                    """,
                    (key, old_value, new_value, usuario),
                )


def save_persistent_rates(values: dict[str, Any]) -> tuple[bool, str]:
    """Save rate configuration locally and, when secrets exist, to GitHub."""
    payload = _normalize_payload(values)
    LOCAL_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOCAL_CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    repo, token = _github_repo_and_token()
    if not repo or not token:
        return True, "Guardado local. Falta GITHUB_REPO o GITHUB_TOKEN para persistencia remota."

    url = _remote_url(repo)
    ok_get, current = _github_request(url, token, method="GET")
    sha = current.get("sha") if ok_get and isinstance(current, dict) else None
    content = base64.b64encode(json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")).decode("ascii")
    body: dict[str, Any] = {
        "message": "Actualizar configuracion persistente de tasas",
        "content": content,
    }
    if sha:
        body["sha"] = sha
    ok_put, result = _github_request(url, token, method="PUT", payload=body)
    if ok_put:
        return True, "Guardado local y remoto en GitHub."
    return False, f"Guardado local, pero falló GitHub: {result}"


def load_persistent_rates() -> dict[str, Any]:
    """Load persistent rates from GitHub first, then local file."""
    repo, token = _github_repo_and_token()
    if repo and token:
        ok, current = _github_request(_remote_url(repo), token, method="GET")
        if ok and isinstance(current, dict) and current.get("content"):
            try:
                raw = base64.b64decode(str(current["content"]).replace("\n", "")).decode("utf-8")
                payload = json.loads(raw)
                rates = payload.get("rates", {})
                if isinstance(rates, dict):
                    return {key: rates[key] for key in RATE_CONFIG_KEYS if key in rates}
            except Exception:
                pass

    if LOCAL_CONFIG_PATH.exists():
        try:
            payload = json.loads(LOCAL_CONFIG_PATH.read_text(encoding="utf-8"))
            rates = payload.get("rates", {})
            if isinstance(rates, dict):
                return {key: rates[key] for key in RATE_CONFIG_KEYS if key in rates}
        except Exception:
            pass
    return {}


def restore_persistent_rates_to_db(usuario: str = "Sistema") -> None:
    rates = load_persistent_rates()
    if not rates:
        return
    try:
        _upsert_rates_direct(rates, usuario)
    except sqlite3.IntegrityError:
        # A concurrent boot can insert the same defaults. Ignore and let the app continue.
        pass
    except Exception:
        # Rate restore must never stop the ERP from starting.
        pass

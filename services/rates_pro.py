from __future__ import annotations

import sqlite3
from typing import Dict, Any

DB_PATH = "database/app.db"

DEFAULT_RATES = {
    "tasa_bcv": 0.0,
    "tasa_binance": 0.0,
    "kontigo_entrada": 0.0,
    "kontigo_salida": 0.0,
}


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def ensure_rates_table() -> None:
    with _get_conn() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS rates_config (
            key TEXT PRIMARY KEY,
            value REAL NOT NULL DEFAULT 0
        )
        """)
        
        for k, v in DEFAULT_RATES.items():
            conn.execute(
                "INSERT OR IGNORE INTO rates_config(key, value) VALUES(?, ?)"
                , (k, v)
            )
        conn.commit()


def get_rates() -> Dict[str, float]:
    ensure_rates_table()
    with _get_conn() as conn:
        rows = conn.execute("SELECT key, value FROM rates_config").fetchall()
        return {row["key"]: float(row["value"] or 0) for row in rows}


def get_rate(key: str) -> float:
    return get_rates().get(key, 0.0)


def set_rate(key: str, value: float) -> None:
    ensure_rates_table()
    with _get_conn() as conn:
        conn.execute(
            "INSERT INTO rates_config(key, value) VALUES(?, ?)\n             ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, float(value))
        )
        conn.commit()


def update_rates(data: Dict[str, Any]) -> None:
    for k, v in data.items():
        set_rate(k, v)


def get_operational_rates() -> Dict[str, float]:
    r = get_rates()
    return {
        "BCV": r.get("tasa_bcv", 0),
        "Binance": r.get("tasa_binance", 0),
        "Kontigo Entrada": r.get("kontigo_entrada", 0),
        "Kontigo Salida": r.get("kontigo_salida", 0),
    }

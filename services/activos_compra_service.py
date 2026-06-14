from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text


TIPOS_ACTIVO_COMPRA = [
    "Impresora",
    "Computadora",
    "Corte",
    "Sublimación",
    "Herramienta",
    "Mobiliario",
    "Otro",
]


def _table_columns(conn: Any, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_activos_compra_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activos_comprados (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                nombre TEXT NOT NULL,
                tipo_activo TEXT NOT NULL DEFAULT 'Otro',
                proveedor TEXT,
                factura TEXT,
                factura_compra_id INTEGER,
                factura_linea_id INTEGER,
                cantidad REAL NOT NULL DEFAULT 1,
                costo_total_usd REAL NOT NULL DEFAULT 0,
                costo_unitario_usd REAL NOT NULL DEFAULT 0,
                fecha_compra TEXT,
                estado TEXT NOT NULL DEFAULT 'activo',
                ubicacion TEXT,
                notas TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activos_comprados_estado ON activos_comprados(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_activos_comprados_factura ON activos_comprados(factura_compra_id)")


def registrar_activo_desde_factura_conn(
    conn: Any,
    *,
    usuario: str,
    nombre: str,
    tipo_activo: str = "Otro",
    proveedor: str = "",
    factura: str = "",
    factura_compra_id: int | None = None,
    factura_linea_id: int | None = None,
    cantidad: float = 1.0,
    costo_total_usd: float = 0.0,
    fecha_compra: str = "",
    notas: str = "",
) -> dict[str, Any]:
    nombre_ok = require_text(nombre, "Nombre del activo")
    cantidad_ok = max(1.0, float(cantidad or 1.0))
    total = max(0.0, float(costo_total_usd or 0.0))
    unitario = total / cantidad_ok if cantidad_ok else total
    tipo = clean_text(tipo_activo) or "Otro"
    cur = conn.execute(
        """
        INSERT INTO activos_comprados
        (usuario, nombre, tipo_activo, proveedor, factura, factura_compra_id, factura_linea_id,
         cantidad, costo_total_usd, costo_unitario_usd, fecha_compra, notas)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULLIF(?, ''), ?)
        """,
        (
            str(usuario or "Sistema"),
            nombre_ok,
            tipo,
            clean_text(proveedor),
            clean_text(factura),
            int(factura_compra_id) if factura_compra_id else None,
            int(factura_linea_id) if factura_linea_id else None,
            round(cantidad_ok, 4),
            round(total, 4),
            round(unitario, 6),
            clean_text(fecha_compra),
            clean_text(notas),
        ),
    )
    return {
        "activo_comprado_id": int(cur.lastrowid),
        "activo_costo_total_usd": round(total, 4),
        "activo_costo_unitario_usd": round(unitario, 6),
    }


def registrar_activo_comprado(**kwargs) -> int:
    ensure_activos_compra_tables()
    with db_transaction() as conn:
        result = registrar_activo_desde_factura_conn(conn, **kwargs)
        return int(result["activo_comprado_id"])


def listar_activos_comprados(limit: int = 200) -> pd.DataFrame:
    ensure_activos_compra_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha_creacion, nombre, tipo_activo, proveedor, factura, factura_compra_id,
                   factura_linea_id, cantidad, costo_total_usd, costo_unitario_usd, fecha_compra,
                   estado, ubicacion, notas
            FROM activos_comprados
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )

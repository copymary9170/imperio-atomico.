from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text


CATEGORIAS_GASTO_OPERATIVO = [
    "Internet",
    "Electricidad",
    "Software",
    "Mantenimiento",
    "Delivery",
    "Comisiones",
    "Servicio técnico",
    "Limpieza",
    "Administrativo",
    "Otro",
]


def ensure_gastos_operativos_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gastos_operativos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                fecha_gasto TEXT,
                categoria TEXT NOT NULL DEFAULT 'Otro',
                concepto TEXT NOT NULL,
                proveedor TEXT,
                factura TEXT,
                factura_compra_id INTEGER,
                factura_linea_id INTEGER,
                monto_usd REAL NOT NULL DEFAULT 0,
                metodo_pago TEXT,
                tipo_pago TEXT,
                estado TEXT NOT NULL DEFAULT 'activo',
                notas TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gastos_operativos_fecha ON gastos_operativos(fecha_creacion)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gastos_operativos_categoria ON gastos_operativos(categoria)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gastos_operativos_factura ON gastos_operativos(factura_compra_id)")


def _inferir_categoria(concepto: str, tipo_linea: str = "") -> str:
    texto = f"{concepto} {tipo_linea}".lower()
    if "internet" in texto or "wifi" in texto:
        return "Internet"
    if "electric" in texto or "luz" in texto:
        return "Electricidad"
    if "adobe" in texto or "software" in texto or "canva" in texto:
        return "Software"
    if "mantenimiento" in texto or "repar" in texto or "servicio técnico" in texto or "servicio tecnico" in texto:
        return "Mantenimiento"
    if "delivery" in texto or "envío" in texto or "envio" in texto or "transporte" in texto:
        return "Delivery"
    if "comision" in texto or "comisión" in texto or "banco" in texto:
        return "Comisiones"
    if "servicio" in texto:
        return "Servicio técnico"
    return "Otro"


def registrar_gasto_operativo_desde_factura_conn(
    conn: Any,
    *,
    usuario: str,
    concepto: str,
    tipo_linea: str = "Gasto",
    proveedor: str = "",
    factura: str = "",
    factura_compra_id: int | None = None,
    factura_linea_id: int | None = None,
    monto_usd: float = 0.0,
    fecha_gasto: str = "",
    metodo_pago: str = "",
    tipo_pago: str = "",
    notas: str = "",
) -> dict[str, Any]:
    concepto_ok = require_text(concepto, "Concepto del gasto")
    monto = max(0.0, float(monto_usd or 0.0))
    categoria = _inferir_categoria(concepto_ok, tipo_linea)
    cur = conn.execute(
        """
        INSERT INTO gastos_operativos
        (usuario, fecha_gasto, categoria, concepto, proveedor, factura, factura_compra_id,
         factura_linea_id, monto_usd, metodo_pago, tipo_pago, notas)
        VALUES (?, NULLIF(?, ''), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(usuario or "Sistema"),
            clean_text(fecha_gasto),
            categoria,
            concepto_ok,
            clean_text(proveedor),
            clean_text(factura),
            int(factura_compra_id) if factura_compra_id else None,
            int(factura_linea_id) if factura_linea_id else None,
            round(monto, 4),
            clean_text(metodo_pago).lower(),
            clean_text(tipo_pago).lower(),
            clean_text(notas),
        ),
    )
    return {"gasto_operativo_id": int(cur.lastrowid), "gasto_categoria": categoria, "gasto_monto_usd": round(monto, 4)}


def listar_gastos_operativos(limit: int = 300) -> pd.DataFrame:
    ensure_gastos_operativos_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha_creacion, fecha_gasto, categoria, concepto, proveedor, factura,
                   factura_compra_id, factura_linea_id, monto_usd, metodo_pago, tipo_pago,
                   estado, notas
            FROM gastos_operativos
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )

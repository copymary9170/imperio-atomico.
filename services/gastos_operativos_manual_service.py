from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text, as_positive
from services.tesoreria_service import registrar_egreso


CATEGORIAS_GASTO_MANUAL = [
    "Internet",
    "Electricidad",
    "Software",
    "Mantenimiento",
    "Delivery",
    "Comisiones",
    "Publicidad",
    "Nomina",
    "Pago hermanas",
    "Papeleria",
    "Limpieza",
    "Transporte",
    "Pasajes",
    "Recarga telefonica",
    "Impuestos",
    "SENIAT",
    "BCV",
    "IGTF",
    "Servicios",
    "Otros",
]


def ensure_gastos_operativos_manual_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gastos_operativos_manual (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha TEXT NOT NULL,
                usuario TEXT,
                categoria TEXT NOT NULL,
                concepto TEXT NOT NULL,
                proveedor TEXT,
                monto_usd REAL NOT NULL DEFAULT 0,
                moneda TEXT DEFAULT 'USD',
                metodo_pago TEXT,
                cuenta_origen TEXT,
                tiene_factura INTEGER DEFAULT 0,
                es_deducible INTEGER DEFAULT 0,
                comprobante TEXT,
                observaciones TEXT,
                movimiento_tesoreria_id INTEGER,
                fecha_creacion TEXT DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(gastos_operativos_manual)").fetchall()}
        migrations = {
            "movimiento_tesoreria_id": "INTEGER",
            "cuenta_origen": "TEXT",
            "comprobante": "TEXT",
            "tiene_factura": "INTEGER DEFAULT 0",
            "es_deducible": "INTEGER DEFAULT 0",
        }
        for column, ddl in migrations.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE gastos_operativos_manual ADD COLUMN {column} {ddl}")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gasto_manual_fecha ON gastos_operativos_manual(fecha)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_gasto_manual_categoria ON gastos_operativos_manual(categoria)")


def registrar_gasto_manual(
    *,
    usuario: str,
    fecha: str,
    categoria: str,
    concepto: str,
    proveedor: str = "",
    monto_usd: float = 0.0,
    moneda: str = "USD",
    metodo_pago: str = "efectivo",
    cuenta_origen: str = "",
    tiene_factura: bool = False,
    es_deducible: bool = False,
    comprobante: str = "",
    observaciones: str = "",
) -> dict[str, Any]:
    ensure_gastos_operativos_manual_tables()
    fecha_ok = require_text(fecha, "Fecha")
    categoria_ok = clean_text(categoria) or "Otros"
    concepto_ok = require_text(concepto, "Concepto")
    monto = as_positive(monto_usd, "Monto", allow_zero=False)
    moneda_ok = clean_text(moneda).upper() or "USD"
    metodo_ok = clean_text(metodo_pago).lower() or "efectivo"

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO gastos_operativos_manual
            (fecha, usuario, categoria, concepto, proveedor, monto_usd, moneda, metodo_pago,
             cuenta_origen, tiene_factura, es_deducible, comprobante, observaciones)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                fecha_ok,
                str(usuario or "Sistema"),
                categoria_ok,
                concepto_ok,
                clean_text(proveedor),
                round(float(monto), 4),
                moneda_ok,
                metodo_ok,
                clean_text(cuenta_origen),
                1 if tiene_factura else 0,
                1 if es_deducible else 0,
                clean_text(comprobante),
                clean_text(observaciones),
            ),
        )
        gasto_id = int(cur.lastrowid)
        movimiento_id = registrar_egreso(
            conn,
            origen="gasto_manual",
            referencia_id=gasto_id,
            descripcion=concepto_ok,
            monto_usd=float(monto),
            moneda=moneda_ok,
            monto_moneda=float(monto),
            tasa_cambio=1.0,
            metodo_pago=metodo_ok,
            usuario=str(usuario or "Sistema"),
            fecha=fecha_ok,
            metadata={
                "modulo": "gastos_operativos_manual",
                "gasto_id": gasto_id,
                "categoria": categoria_ok,
                "proveedor": clean_text(proveedor),
                "cuenta_origen": clean_text(cuenta_origen),
            },
        )
        conn.execute(
            "UPDATE gastos_operativos_manual SET movimiento_tesoreria_id=? WHERE id=?",
            (movimiento_id, gasto_id),
        )
    return {"gasto_id": gasto_id, "movimiento_tesoreria_id": movimiento_id, "monto_usd": round(float(monto), 4)}


def listar_gastos_operativos_manual(limit: int = 500) -> pd.DataFrame:
    ensure_gastos_operativos_manual_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha, usuario, categoria, concepto, proveedor, monto_usd, moneda,
                   metodo_pago, cuenta_origen, tiene_factura, es_deducible, comprobante,
                   observaciones, movimiento_tesoreria_id, fecha_creacion
            FROM gastos_operativos_manual
            ORDER BY date(fecha) DESC, id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )

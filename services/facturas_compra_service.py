from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text
from services.materia_prima_service import listar_materia_prima, registrar_factura_materia_prima


TIPOS_LINEA_FACTURA = [
    "Materia prima",
    "Mercancia para reventa",
    "Activo / equipo",
    "Gasto",
    "Servicio",
]


def ensure_facturas_compra_tables() -> None:
    with db_transaction() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facturas_compra (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fecha_creacion TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                usuario TEXT NOT NULL DEFAULT 'Sistema',
                proveedor TEXT,
                numero_factura TEXT,
                fecha_factura TEXT,
                moneda TEXT NOT NULL DEFAULT 'USD',
                tasa_cambio REAL NOT NULL DEFAULT 1,
                metodo_pago TEXT NOT NULL DEFAULT 'efectivo',
                tipo_pago TEXT NOT NULL DEFAULT 'contado',
                fecha_vencimiento TEXT,
                subtotal_usd REAL NOT NULL DEFAULT 0,
                descuento_usd REAL NOT NULL DEFAULT 0,
                impuesto_usd REAL NOT NULL DEFAULT 0,
                delivery_usd REAL NOT NULL DEFAULT 0,
                comision_usd REAL NOT NULL DEFAULT 0,
                otros_gastos_usd REAL NOT NULL DEFAULT 0,
                total_usd REAL NOT NULL DEFAULT 0,
                pagado_usd REAL NOT NULL DEFAULT 0,
                pendiente_usd REAL NOT NULL DEFAULT 0,
                estado TEXT NOT NULL DEFAULT 'pendiente',
                observaciones TEXT,
                origen TEXT NOT NULL DEFAULT 'facturas_compra'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facturas_compra_lineas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                factura_id INTEGER NOT NULL,
                tipo_linea TEXT NOT NULL DEFAULT 'Materia prima',
                inventario_id INTEGER,
                descripcion TEXT NOT NULL,
                cantidad REAL NOT NULL DEFAULT 0,
                unidad TEXT NOT NULL DEFAULT 'unidad',
                subtotal_usd REAL NOT NULL DEFAULT 0,
                costo_unitario_estimado_usd REAL NOT NULL DEFAULT 0,
                costo_unitario_real_usd REAL NOT NULL DEFAULT 0,
                total_real_linea_usd REAL NOT NULL DEFAULT 0,
                referencia_generada TEXT,
                FOREIGN KEY(factura_id) REFERENCES facturas_compra(id),
                FOREIGN KEY(inventario_id) REFERENCES inventario(id)
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facturas_compra_fecha ON facturas_compra(fecha_creacion)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facturas_compra_estado ON facturas_compra(estado)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_facturas_compra_lineas_factura ON facturas_compra_lineas(factura_id)")


def calcular_estado_factura(total: float, pagado: float) -> str:
    if float(pagado or 0.0) <= 0:
        return "pendiente"
    if float(pagado or 0.0) + 0.0001 >= float(total or 0.0):
        return "pagada"
    return "parcial"


def registrar_factura_compra(
    *,
    usuario: str,
    proveedor: str,
    numero_factura: str,
    fecha_factura: str = "",
    fecha_vencimiento: str = "",
    lineas: list[dict[str, Any]],
    descuento_total_usd: float = 0.0,
    impuestos_pct: float = 0.0,
    delivery_total_usd: float = 0.0,
    comision_total_usd: float = 0.0,
    otros_gastos_usd: float = 0.0,
    moneda_pago: str = "USD",
    tasa_cambio: float = 1.0,
    metodo_pago: str = "efectivo",
    tipo_pago: str = "contado",
    monto_pagado_inicial_usd: float | None = None,
    observaciones: str = "",
) -> dict[str, Any]:
    ensure_facturas_compra_tables()
    lineas_ok: list[dict[str, Any]] = []
    for linea in lineas:
        cantidad = float(linea.get("cantidad") or 0.0)
        subtotal = float(linea.get("subtotal_usd") or 0.0)
        descripcion = clean_text(linea.get("descripcion") or linea.get("item") or "")
        if cantidad > 0 and subtotal > 0 and descripcion:
            lineas_ok.append(
                {
                    "tipo_linea": clean_text(linea.get("tipo_linea") or "Materia prima") or "Materia prima",
                    "inventario_id": int(linea["inventario_id"]) if linea.get("inventario_id") else None,
                    "descripcion": descripcion,
                    "cantidad": cantidad,
                    "unidad": clean_text(linea.get("unidad") or "unidad") or "unidad",
                    "subtotal_usd": subtotal,
                }
            )
    if not lineas_ok:
        raise ValueError("Agrega al menos una línea válida a la factura.")

    subtotal = sum(float(x["subtotal_usd"]) for x in lineas_ok)
    descuento = min(max(0.0, float(descuento_total_usd or 0.0)), subtotal)
    base_desc = subtotal - descuento + max(0.0, float(otros_gastos_usd or 0.0))
    impuesto_total = base_desc * (max(0.0, float(impuestos_pct or 0.0)) / 100.0)
    total = base_desc + impuesto_total + max(0.0, float(delivery_total_usd or 0.0)) + max(0.0, float(comision_total_usd or 0.0))
    pagado = total if monto_pagado_inicial_usd is None else max(0.0, float(monto_pagado_inicial_usd or 0.0))
    pendiente = max(0.0, total - pagado)
    estado = calcular_estado_factura(total, pagado)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO facturas_compra
            (
                usuario, proveedor, numero_factura, fecha_factura, moneda, tasa_cambio,
                metodo_pago, tipo_pago, fecha_vencimiento, subtotal_usd, descuento_usd,
                impuesto_usd, delivery_usd, comision_usd, otros_gastos_usd, total_usd,
                pagado_usd, pendiente_usd, estado, observaciones
            )
            VALUES (?, ?, ?, NULLIF(?, ''), ?, ?, ?, ?, NULLIF(?, ''), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema"),
                clean_text(proveedor),
                clean_text(numero_factura),
                clean_text(fecha_factura),
                clean_text(moneda_pago).upper() or "USD",
                float(tasa_cambio or 1.0),
                clean_text(metodo_pago).lower() or "efectivo",
                clean_text(tipo_pago).lower() or "contado",
                clean_text(fecha_vencimiento),
                round(subtotal, 4),
                round(descuento, 4),
                round(impuesto_total, 4),
                round(float(delivery_total_usd or 0.0), 4),
                round(float(comision_total_usd or 0.0), 4),
                round(float(otros_gastos_usd or 0.0), 4),
                round(total, 4),
                round(pagado, 4),
                round(pendiente, 4),
                estado,
                clean_text(observaciones),
            ),
        )
        factura_id = int(cur.lastrowid)

        for linea in lineas_ok:
            proporcion = linea["subtotal_usd"] / subtotal if subtotal else 0
            descuento_linea = descuento * proporcion
            otros_linea = max(0.0, float(otros_gastos_usd or 0.0)) * proporcion
            base_linea = linea["subtotal_usd"] - descuento_linea + otros_linea
            impuesto_linea = impuesto_total * proporcion
            delivery_linea = max(0.0, float(delivery_total_usd or 0.0)) * proporcion
            comision_linea = max(0.0, float(comision_total_usd or 0.0)) * proporcion
            total_linea = base_linea + impuesto_linea + delivery_linea + comision_linea
            costo_unitario = total_linea / linea["cantidad"] if linea["cantidad"] else 0
            conn.execute(
                """
                INSERT INTO facturas_compra_lineas
                (
                    factura_id, tipo_linea, inventario_id, descripcion, cantidad, unidad,
                    subtotal_usd, costo_unitario_estimado_usd, costo_unitario_real_usd,
                    total_real_linea_usd, referencia_generada
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    factura_id,
                    linea["tipo_linea"],
                    linea["inventario_id"],
                    linea["descripcion"],
                    linea["cantidad"],
                    linea["unidad"],
                    round(linea["subtotal_usd"], 4),
                    round(linea["subtotal_usd"] / linea["cantidad"], 6),
                    round(costo_unitario, 6),
                    round(total_linea, 4),
                    f"Factura compra #{factura_id} · {clean_text(numero_factura) or 'S/N'}",
                ),
            )

    materia_prima_lineas = [
        {
            "inventario_id": x["inventario_id"],
            "cantidad": x["cantidad"],
            "subtotal_usd": x["subtotal_usd"],
        }
        for x in lineas_ok
        if x["tipo_linea"].lower().startswith("materia") and x.get("inventario_id")
    ]
    if materia_prima_lineas:
        registrar_factura_materia_prima(
            usuario=usuario,
            proveedor=proveedor,
            factura=f"FC-{factura_id} {numero_factura}",
            lineas=materia_prima_lineas,
            delivery_total_usd=delivery_total_usd,
            impuestos_pct=impuestos_pct,
            comision_total_usd=comision_total_usd,
            descuento_total_usd=descuento_total_usd,
            otros_gastos_usd=otros_gastos_usd,
            moneda_pago=moneda_pago,
            tasa_cambio=tasa_cambio,
            metodo_pago=metodo_pago,
            tipo_pago=tipo_pago,
            monto_pagado_inicial_usd=monto_pagado_inicial_usd,
            referencia=f"Factura de compra #{factura_id}",
        )

    return {
        "factura_id": factura_id,
        "subtotal_usd": round(subtotal, 4),
        "descuento_usd": round(descuento, 4),
        "impuesto_usd": round(impuesto_total, 4),
        "delivery_usd": round(float(delivery_total_usd or 0.0), 4),
        "comision_usd": round(float(comision_total_usd or 0.0), 4),
        "otros_gastos_usd": round(float(otros_gastos_usd or 0.0), 4),
        "total_usd": round(total, 4),
        "pagado_usd": round(pagado, 4),
        "pendiente_usd": round(pendiente, 4),
        "estado": estado,
        "lineas": lineas_ok,
    }


def listar_facturas_compra(limit: int = 100) -> pd.DataFrame:
    ensure_facturas_compra_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id, fecha_creacion, proveedor, numero_factura, fecha_factura,
                moneda, tasa_cambio, metodo_pago, tipo_pago, fecha_vencimiento,
                subtotal_usd, descuento_usd, impuesto_usd, delivery_usd, comision_usd,
                otros_gastos_usd, total_usd, pagado_usd, pendiente_usd, estado, observaciones
            FROM facturas_compra
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )


def listar_lineas_factura(factura_id: int) -> pd.DataFrame:
    ensure_facturas_compra_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id, tipo_linea, descripcion, cantidad, unidad, subtotal_usd,
                costo_unitario_estimado_usd, costo_unitario_real_usd, total_real_linea_usd,
                inventario_id, referencia_generada
            FROM facturas_compra_lineas
            WHERE factura_id = ?
            ORDER BY id
            """,
            conn,
            params=(int(factura_id),),
        )


def listar_cuentas_por_pagar(limit: int = 100) -> pd.DataFrame:
    ensure_facturas_compra_tables()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id, proveedor, numero_factura, fecha_factura, fecha_vencimiento,
                total_usd, pagado_usd, pendiente_usd, estado, metodo_pago, tipo_pago
            FROM facturas_compra
            WHERE pendiente_usd > 0.0001 OR estado IN ('pendiente', 'parcial')
            ORDER BY
                CASE WHEN fecha_vencimiento IS NULL THEN 1 ELSE 0 END,
                fecha_vencimiento,
                id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )

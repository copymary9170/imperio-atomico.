from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text, as_positive
from services.costo_real_compra_service import calcular_costo_real_compra
from services.tesoreria_service import registrar_egreso


MATERIA_PRIMA_CATEGORIAS = [
    "Materia prima",
    "Papel",
    "Tinta",
    "Toner",
    "Cartucho",
    "Cabezal",
    "Sublimacion",
    "Papeleria",
    "Empaque",
    "Rollo termico",
    "Vinil / adhesivo",
    "Otro insumo",
]

UNIDADES_MATERIA_PRIMA = [
    "unidad",
    "hoja",
    "resma",
    "cartucho",
    "toner",
    "botella",
    "rollo",
    "paquete",
    "caja",
]

UNIDADES_TECNICAS = [
    "no aplica",
    "ml",
    "litro",
    "gramo",
    "kg",
    "cm",
    "metro",
    "hoja",
    "unidad",
]

MASTER_FIELD_COLUMNS: dict[str, str] = {
    "proveedor_principal": "TEXT",
    "proveedor_alternativo": "TEXT",
    "marca": "TEXT",
    "fabricante": "TEXT",
    "codigo_fabricante": "TEXT",
    "ubicacion": "TEXT",
    "stock_maximo": "REAL NOT NULL DEFAULT 0",
    "unidad_tecnica": "TEXT NOT NULL DEFAULT 'no aplica'",
    "contenido_tecnico": "REAL NOT NULL DEFAULT 0",
    "rendimiento_estimado": "REAL NOT NULL DEFAULT 0",
    "compatible_con": "TEXT",
}


def _table_columns(conn: Any, table_name: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def ensure_materia_prima_master_fields() -> None:
    with db_transaction() as conn:
        columns = _table_columns(conn, "inventario")
        for column, ddl_type in MASTER_FIELD_COLUMNS.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE inventario ADD COLUMN {column} {ddl_type}")
                columns.add(column)


def listar_materia_prima() -> pd.DataFrame:
    ensure_materia_prima_master_fields()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT
                id, fecha, sku, nombre, categoria, proveedor_principal, marca,
                unidad, stock_actual, stock_minimo, stock_maximo, ubicacion,
                unidad_tecnica, contenido_tecnico, rendimiento_estimado, compatible_con,
                costo_unitario_usd, precio_venta_usd, estado
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY categoria, nombre
            """,
            conn,
        )


def crear_materia_prima(
    *,
    usuario: str,
    sku: str,
    nombre: str,
    categoria: str,
    unidad: str,
    stock_minimo: float = 0.0,
    precio_venta_usd: float = 0.0,
    proveedor_principal: str = "",
    proveedor_alternativo: str = "",
    marca: str = "",
    fabricante: str = "",
    codigo_fabricante: str = "",
    ubicacion: str = "",
    stock_maximo: float = 0.0,
    unidad_tecnica: str = "no aplica",
    contenido_tecnico: float = 0.0,
    rendimiento_estimado: float = 0.0,
    compatible_con: str = "",
) -> int:
    ensure_materia_prima_master_fields()
    sku_ok = require_text(sku, "SKU")
    nombre_ok = require_text(nombre, "Nombre")
    categoria_ok = clean_text(categoria) or "Materia prima"
    unidad_ok = clean_text(unidad) or "unidad"

    with db_transaction() as conn:
        existe = conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?)", (sku_ok,)).fetchone()
        if existe:
            raise ValueError(f"Ya existe un item con SKU {sku_ok}.")
        cur = conn.execute(
            """
            INSERT INTO inventario
            (
                usuario, sku, nombre, categoria, unidad, stock_actual, stock_minimo,
                costo_unitario_usd, precio_venta_usd, creado_por, creado_en,
                proveedor_principal, proveedor_alternativo, marca, fabricante,
                codigo_fabricante, ubicacion, stock_maximo, unidad_tecnica,
                contenido_tecnico, rendimiento_estimado, compatible_con
            )
            VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(usuario or "Sistema"),
                sku_ok,
                nombre_ok,
                categoria_ok,
                unidad_ok,
                max(0.0, float(stock_minimo or 0.0)),
                max(0.0, float(precio_venta_usd or 0.0)),
                str(usuario or "Sistema"),
                clean_text(proveedor_principal),
                clean_text(proveedor_alternativo),
                clean_text(marca),
                clean_text(fabricante),
                clean_text(codigo_fabricante),
                clean_text(ubicacion),
                max(0.0, float(stock_maximo or 0.0)),
                clean_text(unidad_tecnica) or "no aplica",
                max(0.0, float(contenido_tecnico or 0.0)),
                max(0.0, float(rendimiento_estimado or 0.0)),
                clean_text(compatible_con),
            ),
        )
        return int(cur.lastrowid)


def registrar_compra_materia_prima(
    *,
    usuario: str,
    inventario_id: int,
    cantidad_comprada: float,
    costo_base_usd: float,
    impuestos_pct: float = 0.0,
    delivery_usd: float = 0.0,
    comision_pago_usd: float = 0.0,
    moneda_pago: str = "USD",
    tasa_cambio: float = 1.0,
    metodo_pago: str = "efectivo",
    tipo_pago: str = "contado",
    monto_pagado_inicial_usd: float | None = None,
    referencia: str = "",
    proveedor: str = "",
    factura: str = "",
    otros_gastos_usd: float = 0.0,
) -> dict[str, Any]:
    ensure_materia_prima_master_fields()
    cantidad = as_positive(cantidad_comprada, "Cantidad comprada", allow_zero=False)
    costo_base = as_positive(costo_base_usd, "Costo base", allow_zero=False)
    costo = calcular_costo_real_compra(
        costo_base_usd=costo_base + max(0.0, float(otros_gastos_usd or 0.0)),
        cantidad=cantidad,
        impuestos_pct=float(impuestos_pct or 0.0),
        delivery_usd=float(delivery_usd or 0.0),
        comision_pago_usd=float(comision_pago_usd or 0.0),
    )
    pago_inicial = costo.total_real_usd if monto_pagado_inicial_usd is None else max(0.0, float(monto_pagado_inicial_usd or 0.0))
    saldo = max(0.0, costo.total_real_usd - pago_inicial)

    with db_transaction() as conn:
        row = conn.execute(
            "SELECT id, nombre, unidad, stock_actual, costo_unitario_usd FROM inventario WHERE id=? AND COALESCE(estado,'activo')='activo'",
            (int(inventario_id),),
        ).fetchone()
        if not row:
            raise ValueError("Materia prima no encontrada o inactiva.")

        stock_anterior = float(row["stock_actual"] or 0.0)
        costo_anterior = float(row["costo_unitario_usd"] or 0.0)
        stock_nuevo = stock_anterior + cantidad
        costo_promedio = ((stock_anterior * costo_anterior) + (cantidad * costo.costo_unitario_real_usd)) / stock_nuevo if stock_nuevo > 0 else costo.costo_unitario_real_usd

        update_extra = ""
        params_extra: list[Any] = []
        if clean_text(proveedor):
            update_extra = ", proveedor_principal = ?"
            params_extra.append(clean_text(proveedor))

        conn.execute(
            f"""
            UPDATE inventario
            SET stock_actual = ?, costo_unitario_usd = ?, actualizado_por = ?, actualizado_en = CURRENT_TIMESTAMP{update_extra}
            WHERE id = ?
            """,
            (stock_nuevo, round(costo_promedio, 6), str(usuario or "Sistema"), *params_extra, int(inventario_id)),
        )

        ref = (
            f"Compra materia prima | Proveedor: {clean_text(proveedor) or 'N/D'} | Factura: {clean_text(factura) or 'N/D'} | "
            f"Cantidad: {cantidad:g} {row['unidad']} | Base: ${costo_base:,.2f} | Otros: ${float(otros_gastos_usd or 0):,.2f} | "
            f"Impuesto: ${costo.impuesto_usd:,.2f} | Delivery: ${costo.delivery_usd:,.2f} | Comision: ${costo.comision_pago_usd:,.2f}"
        )
        if clean_text(referencia):
            ref += f" | {clean_text(referencia)}"

        conn.execute(
            """
            INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
            VALUES (?, ?, 'entrada', ?, ?, ?)
            """,
            (str(usuario or "Sistema"), int(inventario_id), cantidad, round(costo.costo_unitario_real_usd, 6), ref),
        )

        columns = _table_columns(conn, "historial_compras")
        base_cols = [
            "usuario", "inventario_id", "item", "cantidad", "unidad", "costo_total_usd", "costo_unit_usd",
            "impuestos", "delivery", "moneda_pago", "tipo_pago", "metodo_pago",
            "monto_pagado_inicial_usd", "saldo_pendiente_usd",
        ]
        values: list[Any] = [
            str(usuario or "Sistema"), int(inventario_id), str(row["nombre"]), cantidad, str(row["unidad"]),
            float(costo.total_real_usd), float(costo.costo_unitario_real_usd), float(impuestos_pct or 0.0),
            float(delivery_usd or 0.0), clean_text(moneda_pago).upper() or "USD", clean_text(tipo_pago).lower() or "contado",
            clean_text(metodo_pago).lower() or "efectivo", float(pago_inicial), float(saldo),
        ]
        if "comision_pago_usd" in columns:
            base_cols.append("comision_pago_usd")
            values.append(float(comision_pago_usd or 0.0))
        if "tasa_usada" in columns:
            base_cols.append("tasa_usada")
            values.append(float(tasa_cambio or 1.0))

        placeholders = ", ".join(["?"] * len(base_cols))
        cur = conn.execute(
            f"INSERT INTO historial_compras ({', '.join(base_cols)}) VALUES ({placeholders})",
            tuple(values),
        )
        compra_id = int(cur.lastrowid)

        if pago_inicial > 0:
            registrar_egreso(
                conn,
                origen="compra_inicial_pagada",
                referencia_id=compra_id,
                descripcion=f"Compra materia prima #{compra_id} · {row['nombre']}",
                monto_usd=float(pago_inicial),
                moneda=clean_text(moneda_pago).upper() or "USD",
                monto_moneda=float(pago_inicial) if clean_text(moneda_pago).upper() == "USD" else float(pago_inicial) * float(tasa_cambio or 1.0),
                tasa_cambio=float(tasa_cambio or 1.0),
                metodo_pago=clean_text(metodo_pago).lower() or "efectivo",
                usuario=str(usuario or "Sistema"),
                metadata={
                    "modulo": "materia_prima",
                    "compra_id": compra_id,
                    "inventario_id": int(inventario_id),
                    "proveedor": clean_text(proveedor),
                    "factura": clean_text(factura),
                    "cantidad_comprada": cantidad,
                    "stock_anterior": stock_anterior,
                    "stock_nuevo": stock_nuevo,
                    "costo_base_usd": costo_base,
                    "otros_gastos_usd": max(0.0, float(otros_gastos_usd or 0.0)),
                    "impuesto_usd": costo.impuesto_usd,
                    "delivery_usd": costo.delivery_usd,
                    "comision_pago_usd": costo.comision_pago_usd,
                    "total_real_usd": costo.total_real_usd,
                },
                allow_duplicate=True,
            )

        return {
            "compra_id": compra_id,
            "stock_anterior": round(stock_anterior, 4),
            "cantidad_comprada": round(cantidad, 4),
            "stock_nuevo": round(stock_nuevo, 4),
            "costo_unitario_real_usd": costo.costo_unitario_real_usd,
            "costo_promedio_usd": round(costo_promedio, 6),
            "total_real_usd": costo.total_real_usd,
            "impuesto_usd": costo.impuesto_usd,
            "delivery_usd": costo.delivery_usd,
            "comision_pago_usd": costo.comision_pago_usd,
        }


def listar_compras_materia_prima(limit: int = 100) -> pd.DataFrame:
    ensure_materia_prima_master_fields()
    with db_transaction() as conn:
        columns = _table_columns(conn, "historial_compras")
        comision_expr = "COALESCE(comision_pago_usd, 0) AS comision_pago_usd" if "comision_pago_usd" in columns else "0 AS comision_pago_usd"
        tasa_expr = "COALESCE(tasa_usada, 1) AS tasa_usada" if "tasa_usada" in columns else "1 AS tasa_usada"
        return pd.read_sql_query(
            f"""
            SELECT
                hc.id, hc.fecha, hc.item, hc.cantidad, hc.unidad,
                hc.costo_total_usd, hc.costo_unit_usd, hc.impuestos, hc.delivery,
                {comision_expr}, hc.moneda_pago, {tasa_expr}, hc.tipo_pago, hc.metodo_pago,
                hc.monto_pagado_inicial_usd, hc.saldo_pendiente_usd,
                i.proveedor_principal, i.marca, i.unidad_tecnica, i.contenido_tecnico,
                i.stock_actual, i.costo_unitario_usd AS costo_promedio_actual
            FROM historial_compras hc
            LEFT JOIN inventario i ON i.id = hc.inventario_id
            WHERE hc.inventario_id IS NOT NULL
            ORDER BY hc.id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )

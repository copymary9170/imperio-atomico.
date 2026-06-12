from __future__ import annotations

from typing import Any

import pandas as pd

from database.connection import db_transaction
from modules.common import clean_text, require_text, as_positive
from services.costo_real_compra_service import calcular_costo_real_compra
from services.tesoreria_service import registrar_egreso


MATERIA_PRIMA_CATEGORIAS = [
    "Materia prima", "Papel", "Tinta", "Toner", "Cartucho", "Cabezal", "Sublimacion", "Papeleria", "Empaque", "Rollo termico", "Vinil / adhesivo", "Otro insumo",
]
UNIDADES_MATERIA_PRIMA = ["unidad", "hoja", "resma", "cartucho", "toner", "botella", "rollo", "paquete", "caja"]
UNIDADES_TECNICAS = ["no aplica", "ml", "litro", "gramo", "kg", "cm", "metro", "hoja", "unidad"]
MASTER_FIELD_COLUMNS: dict[str, str] = {
    "proveedor_principal": "TEXT", "proveedor_alternativo": "TEXT", "marca": "TEXT", "fabricante": "TEXT", "codigo_fabricante": "TEXT", "ubicacion": "TEXT",
    "stock_maximo": "REAL NOT NULL DEFAULT 0", "unidad_tecnica": "TEXT NOT NULL DEFAULT 'no aplica'", "contenido_tecnico": "REAL NOT NULL DEFAULT 0",
    "rendimiento_estimado": "REAL NOT NULL DEFAULT 0", "compatible_con": "TEXT",
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
            SELECT id, fecha, sku, nombre, categoria, proveedor_principal, marca, unidad, stock_actual, stock_minimo, stock_maximo, ubicacion,
                   unidad_tecnica, contenido_tecnico, rendimiento_estimado, compatible_con, costo_unitario_usd, precio_venta_usd, estado
            FROM inventario
            WHERE COALESCE(estado, 'activo') = 'activo'
            ORDER BY categoria, nombre
            """,
            conn,
        )


def crear_materia_prima(*, usuario: str, sku: str, nombre: str, categoria: str, unidad: str, stock_minimo: float = 0.0, precio_venta_usd: float = 0.0,
                         proveedor_principal: str = "", proveedor_alternativo: str = "", marca: str = "", fabricante: str = "", codigo_fabricante: str = "",
                         ubicacion: str = "", stock_maximo: float = 0.0, unidad_tecnica: str = "no aplica", contenido_tecnico: float = 0.0,
                         rendimiento_estimado: float = 0.0, compatible_con: str = "") -> int:
    ensure_materia_prima_master_fields()
    sku_ok = require_text(sku, "SKU")
    nombre_ok = require_text(nombre, "Nombre")
    with db_transaction() as conn:
        existe = conn.execute("SELECT id FROM inventario WHERE lower(sku)=lower(?)", (sku_ok,)).fetchone()
        if existe:
            raise ValueError(f"Ya existe un item con SKU {sku_ok}.")
        cur = conn.execute(
            """
            INSERT INTO inventario
            (usuario, sku, nombre, categoria, unidad, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd, creado_por, creado_en,
             proveedor_principal, proveedor_alternativo, marca, fabricante, codigo_fabricante, ubicacion, stock_maximo, unidad_tecnica, contenido_tecnico, rendimiento_estimado, compatible_con)
            VALUES (?, ?, ?, ?, ?, 0, ?, 0, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(usuario or "Sistema"), sku_ok, nombre_ok, clean_text(categoria) or "Materia prima", clean_text(unidad) or "unidad",
             max(0.0, float(stock_minimo or 0.0)), max(0.0, float(precio_venta_usd or 0.0)), str(usuario or "Sistema"),
             clean_text(proveedor_principal), clean_text(proveedor_alternativo), clean_text(marca), clean_text(fabricante), clean_text(codigo_fabricante), clean_text(ubicacion),
             max(0.0, float(stock_maximo or 0.0)), clean_text(unidad_tecnica) or "no aplica", max(0.0, float(contenido_tecnico or 0.0)),
             max(0.0, float(rendimiento_estimado or 0.0)), clean_text(compatible_con)),
        )
        return int(cur.lastrowid)


def _insertar_compra_linea(conn: Any, *, usuario: str, inventario_id: int, cantidad: float, costo_unitario_real: float, total_linea_real: float,
                           impuestos_pct: float, delivery_asignado: float, comision_asignada: float, moneda_pago: str, tasa_cambio: float,
                           metodo_pago: str, tipo_pago: str, pago_inicial_linea: float, referencia: str, proveedor: str, factura: str) -> dict[str, Any]:
    row = conn.execute("SELECT id, nombre, unidad, stock_actual, costo_unitario_usd FROM inventario WHERE id=? AND COALESCE(estado,'activo')='activo'", (int(inventario_id),)).fetchone()
    if not row:
        raise ValueError("Materia prima no encontrada o inactiva.")
    stock_anterior = float(row["stock_actual"] or 0.0)
    costo_anterior = float(row["costo_unitario_usd"] or 0.0)
    stock_nuevo = stock_anterior + cantidad
    costo_promedio = ((stock_anterior * costo_anterior) + (cantidad * costo_unitario_real)) / stock_nuevo if stock_nuevo > 0 else costo_unitario_real
    extra = ", proveedor_principal = ?" if clean_text(proveedor) else ""
    params_extra = [clean_text(proveedor)] if clean_text(proveedor) else []
    conn.execute(f"UPDATE inventario SET stock_actual=?, costo_unitario_usd=?, actualizado_por=?, actualizado_en=CURRENT_TIMESTAMP{extra} WHERE id=?", (stock_nuevo, round(costo_promedio, 6), str(usuario or "Sistema"), *params_extra, int(inventario_id)))
    conn.execute("INSERT INTO movimientos_inventario(usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia) VALUES (?, ?, 'entrada', ?, ?, ?)", (str(usuario or "Sistema"), int(inventario_id), cantidad, round(costo_unitario_real, 6), referencia))
    columns = _table_columns(conn, "historial_compras")
    cols = ["usuario", "inventario_id", "item", "cantidad", "unidad", "costo_total_usd", "costo_unit_usd", "impuestos", "delivery", "moneda_pago", "tipo_pago", "metodo_pago", "monto_pagado_inicial_usd", "saldo_pendiente_usd"]
    vals: list[Any] = [str(usuario or "Sistema"), int(inventario_id), str(row["nombre"]), cantidad, str(row["unidad"]), float(total_linea_real), float(costo_unitario_real), float(impuestos_pct or 0.0), float(delivery_asignado or 0.0), clean_text(moneda_pago).upper() or "USD", clean_text(tipo_pago).lower() or "contado", clean_text(metodo_pago).lower() or "efectivo", float(pago_inicial_linea), max(0.0, float(total_linea_real) - float(pago_inicial_linea))]
    if "comision_pago_usd" in columns:
        cols.append("comision_pago_usd"); vals.append(float(comision_asignada or 0.0))
    if "tasa_usada" in columns:
        cols.append("tasa_usada"); vals.append(float(tasa_cambio or 1.0))
    cur = conn.execute(f"INSERT INTO historial_compras ({', '.join(cols)}) VALUES ({', '.join(['?'] * len(cols))})", tuple(vals))
    return {"compra_id": int(cur.lastrowid), "item": str(row["nombre"]), "stock_anterior": round(stock_anterior, 4), "stock_nuevo": round(stock_nuevo, 4), "cantidad": round(cantidad, 4), "costo_unitario_real_usd": round(costo_unitario_real, 6), "total_linea_real_usd": round(total_linea_real, 4)}


def registrar_compra_materia_prima(*, usuario: str, inventario_id: int, cantidad_comprada: float, costo_base_usd: float, impuestos_pct: float = 0.0, delivery_usd: float = 0.0,
                                    comision_pago_usd: float = 0.0, moneda_pago: str = "USD", tasa_cambio: float = 1.0, metodo_pago: str = "efectivo", tipo_pago: str = "contado",
                                    monto_pagado_inicial_usd: float | None = None, referencia: str = "", proveedor: str = "", factura: str = "", otros_gastos_usd: float = 0.0) -> dict[str, Any]:
    ensure_materia_prima_master_fields()
    cantidad = as_positive(cantidad_comprada, "Cantidad comprada", allow_zero=False)
    costo_base = as_positive(costo_base_usd, "Costo base", allow_zero=False)
    costo = calcular_costo_real_compra(costo_base_usd=costo_base + max(0.0, float(otros_gastos_usd or 0.0)), cantidad=cantidad, impuestos_pct=float(impuestos_pct or 0.0), delivery_usd=float(delivery_usd or 0.0), comision_pago_usd=float(comision_pago_usd or 0.0))
    pago = costo.total_real_usd if monto_pagado_inicial_usd is None else max(0.0, float(monto_pagado_inicial_usd or 0.0))
    with db_transaction() as conn:
        ref = f"Compra materia prima | Proveedor: {clean_text(proveedor) or 'N/D'} | Factura: {clean_text(factura) or 'N/D'} | Base: ${costo_base:,.2f} | Otros: ${float(otros_gastos_usd or 0):,.2f} | Impuesto: ${costo.impuesto_usd:,.2f} | Delivery: ${costo.delivery_usd:,.2f} | Comision: ${costo.comision_pago_usd:,.2f}"
        if clean_text(referencia): ref += f" | {clean_text(referencia)}"
        result = _insertar_compra_linea(conn, usuario=usuario, inventario_id=inventario_id, cantidad=cantidad, costo_unitario_real=costo.costo_unitario_real_usd, total_linea_real=costo.total_real_usd, impuestos_pct=impuestos_pct, delivery_asignado=delivery_usd, comision_asignada=comision_pago_usd, moneda_pago=moneda_pago, tasa_cambio=tasa_cambio, metodo_pago=metodo_pago, tipo_pago=tipo_pago, pago_inicial_linea=pago, referencia=ref, proveedor=proveedor, factura=factura)
        if pago > 0:
            registrar_egreso(conn, origen="compra_inicial_pagada", referencia_id=result["compra_id"], descripcion=f"Compra materia prima #{result['compra_id']} · {result['item']}", monto_usd=float(pago), moneda=clean_text(moneda_pago).upper() or "USD", monto_moneda=float(pago) if clean_text(moneda_pago).upper() == "USD" else float(pago) * float(tasa_cambio or 1.0), tasa_cambio=float(tasa_cambio or 1.0), metodo_pago=clean_text(metodo_pago).lower() or "efectivo", usuario=str(usuario or "Sistema"), allow_duplicate=True)
        return {**result, "stock_anterior": result["stock_anterior"], "cantidad_comprada": result["cantidad"], "stock_nuevo": result["stock_nuevo"], "costo_promedio_usd": result["costo_unitario_real_usd"], "total_real_usd": costo.total_real_usd, "impuesto_usd": costo.impuesto_usd, "delivery_usd": costo.delivery_usd, "comision_pago_usd": costo.comision_pago_usd}


def registrar_factura_materia_prima(*, usuario: str, proveedor: str, factura: str, lineas: list[dict[str, Any]], delivery_total_usd: float = 0.0, impuestos_pct: float = 0.0,
                                    comision_total_usd: float = 0.0, descuento_total_usd: float = 0.0, otros_gastos_usd: float = 0.0, moneda_pago: str = "USD", tasa_cambio: float = 1.0,
                                    metodo_pago: str = "efectivo", tipo_pago: str = "contado", monto_pagado_inicial_usd: float | None = None, referencia: str = "") -> dict[str, Any]:
    ensure_materia_prima_master_fields()
    lineas_ok = []
    for linea in lineas:
        cantidad = float(linea.get("cantidad") or 0.0)
        subtotal = float(linea.get("subtotal_usd") or 0.0)
        if cantidad > 0 and subtotal > 0 and linea.get("inventario_id"):
            lineas_ok.append({"inventario_id": int(linea["inventario_id"]), "cantidad": cantidad, "subtotal_usd": subtotal})
    if not lineas_ok:
        raise ValueError("Agrega al menos una línea con cantidad y subtotal mayores a cero.")
    subtotal = sum(x["subtotal_usd"] for x in lineas_ok)
    descuento = min(max(0.0, float(descuento_total_usd or 0.0)), subtotal)
    base_desc = subtotal - descuento + max(0.0, float(otros_gastos_usd or 0.0))
    impuesto_total = base_desc * (max(0.0, float(impuestos_pct or 0.0)) / 100.0)
    total_factura = base_desc + impuesto_total + max(0.0, float(delivery_total_usd or 0.0)) + max(0.0, float(comision_total_usd or 0.0))
    pago_total = total_factura if monto_pagado_inicial_usd is None else max(0.0, float(monto_pagado_inicial_usd or 0.0))
    resultados = []
    with db_transaction() as conn:
        for linea in lineas_ok:
            proporcion = linea["subtotal_usd"] / subtotal if subtotal else 0
            descuento_linea = descuento * proporcion
            otros_linea = max(0.0, float(otros_gastos_usd or 0.0)) * proporcion
            base_linea = linea["subtotal_usd"] - descuento_linea + otros_linea
            impuesto_linea = impuesto_total * proporcion
            delivery_linea = max(0.0, float(delivery_total_usd or 0.0)) * proporcion
            comision_linea = max(0.0, float(comision_total_usd or 0.0)) * proporcion
            total_linea = base_linea + impuesto_linea + delivery_linea + comision_linea
            pago_linea = pago_total * (total_linea / total_factura) if total_factura > 0 else 0
            costo_unitario = total_linea / linea["cantidad"]
            ref = f"Factura multiple {clean_text(factura) or 'S/N'} | Proveedor: {clean_text(proveedor) or 'N/D'} | Subtotal linea: ${linea['subtotal_usd']:,.2f} | Desc asignado: ${descuento_linea:,.2f} | Delivery asignado: ${delivery_linea:,.2f} | Comision asignada: ${comision_linea:,.2f}"
            if clean_text(referencia): ref += f" | {clean_text(referencia)}"
            resultados.append(_insertar_compra_linea(conn, usuario=usuario, inventario_id=linea["inventario_id"], cantidad=linea["cantidad"], costo_unitario_real=costo_unitario, total_linea_real=total_linea, impuestos_pct=impuestos_pct, delivery_asignado=delivery_linea, comision_asignada=comision_linea, moneda_pago=moneda_pago, tasa_cambio=tasa_cambio, metodo_pago=metodo_pago, tipo_pago=tipo_pago, pago_inicial_linea=pago_linea, referencia=ref, proveedor=proveedor, factura=factura))
        if pago_total > 0:
            registrar_egreso(conn, origen="compra_inicial_pagada", referencia_id=None, descripcion=f"Factura materia prima {clean_text(factura) or 'S/N'} · {len(resultados)} item(s)", monto_usd=float(pago_total), moneda=clean_text(moneda_pago).upper() or "USD", monto_moneda=float(pago_total) if clean_text(moneda_pago).upper() == "USD" else float(pago_total) * float(tasa_cambio or 1.0), tasa_cambio=float(tasa_cambio or 1.0), metodo_pago=clean_text(metodo_pago).lower() or "efectivo", usuario=str(usuario or "Sistema"), metadata={"modulo": "materia_prima_factura", "factura": clean_text(factura), "proveedor": clean_text(proveedor), "total_factura_usd": round(total_factura, 4), "lineas": resultados}, allow_duplicate=True)
    return {"subtotal_usd": round(subtotal, 4), "descuento_total_usd": round(descuento, 4), "impuesto_total_usd": round(impuesto_total, 4), "delivery_total_usd": round(float(delivery_total_usd or 0.0), 4), "comision_total_usd": round(float(comision_total_usd or 0.0), 4), "otros_gastos_usd": round(float(otros_gastos_usd or 0.0), 4), "total_factura_usd": round(total_factura, 4), "lineas": resultados}


def listar_compras_materia_prima(limit: int = 100) -> pd.DataFrame:
    ensure_materia_prima_master_fields()
    with db_transaction() as conn:
        columns = _table_columns(conn, "historial_compras")
        comision_expr = "COALESCE(comision_pago_usd, 0) AS comision_pago_usd" if "comision_pago_usd" in columns else "0 AS comision_pago_usd"
        tasa_expr = "COALESCE(tasa_usada, 1) AS tasa_usada" if "tasa_usada" in columns else "1 AS tasa_usada"
        return pd.read_sql_query(
            f"""
            SELECT hc.id, hc.fecha, hc.item, hc.cantidad, hc.unidad, hc.costo_total_usd, hc.costo_unit_usd, hc.impuestos, hc.delivery,
                   {comision_expr}, hc.moneda_pago, {tasa_expr}, hc.tipo_pago, hc.metodo_pago, hc.monto_pagado_inicial_usd, hc.saldo_pendiente_usd,
                   i.proveedor_principal, i.marca, i.unidad_tecnica, i.contenido_tecnico, i.stock_actual, i.costo_unitario_usd AS costo_promedio_actual
            FROM historial_compras hc
            LEFT JOIN inventario i ON i.id = hc.inventario_id
            WHERE hc.inventario_id IS NOT NULL
            ORDER BY hc.id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )

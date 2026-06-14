from __future__ import annotations

import pandas as pd

from database.connection import db_transaction


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _sum_table(conn, table: str, column: str, date_column: str, fecha_desde: str = "", fecha_hasta: str = "") -> float:
    if not _table_exists(conn, table):
        return 0.0
    where = []
    params = []
    if fecha_desde:
        where.append(f"date({date_column}) >= date(?)")
        params.append(fecha_desde)
    if fecha_hasta:
        where.append(f"date({date_column}) <= date(?)")
        params.append(fecha_hasta)
    sql = f"SELECT COALESCE(SUM({column}), 0) FROM {table}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    try:
        return float(conn.execute(sql, tuple(params)).fetchone()[0] or 0.0)
    except Exception:
        return 0.0


def generar_estado_resultados(fecha_desde: str = "", fecha_hasta: str = "") -> dict:
    with db_transaction() as conn:
        ventas = _sum_table(conn, "ventas", "total_usd", "fecha", fecha_desde, fecha_hasta)
        compras_mp = _sum_table(conn, "historial_compras", "costo_total_usd", "fecha", fecha_desde, fecha_hasta)
        compras_reventa = _sum_table(conn, "compras_reventa", "costo_total_usd", "fecha", fecha_desde, fecha_hasta)
        facturas_compra = _sum_table(conn, "facturas_compra", "total_usd", "fecha_creacion", fecha_desde, fecha_hasta)
        gastos_legacy = _sum_table(conn, "gastos", "monto_usd", "fecha", fecha_desde, fecha_hasta)
        gastos_factura = _sum_table(conn, "gastos_operativos", "monto_usd", "fecha_creacion", fecha_desde, fecha_hasta)
        gastos_manual = _sum_table(conn, "gastos_operativos_manual", "monto_usd", "fecha", fecha_desde, fecha_hasta)
        egresos = _sum_table(conn, "movimientos_tesoreria", "monto_usd", "fecha", fecha_desde, fecha_hasta)
        cxc_pendiente = _sum_table(conn, "cuentas_por_cobrar", "pendiente_usd", "fecha_creacion", fecha_desde, fecha_hasta)
        cxp_pendiente = _sum_table(conn, "facturas_compra", "pendiente_usd", "fecha_creacion", fecha_desde, fecha_hasta)

    costo_directo = compras_mp + compras_reventa
    utilidad_bruta = ventas - costo_directo
    gastos_operativos = max(gastos_legacy + gastos_factura + gastos_manual, 0.0)
    utilidad_estimada = utilidad_bruta - gastos_operativos

    return {
        "ventas_usd": round(ventas, 4),
        "compras_materia_prima_usd": round(compras_mp, 4),
        "compras_reventa_usd": round(compras_reventa, 4),
        "facturas_compra_usd": round(facturas_compra, 4),
        "costo_directo_usd": round(costo_directo, 4),
        "utilidad_bruta_usd": round(utilidad_bruta, 4),
        "gastos_legacy_usd": round(gastos_legacy, 4),
        "gastos_factura_usd": round(gastos_factura, 4),
        "gastos_manual_usd": round(gastos_manual, 4),
        "gastos_operativos_usd": round(gastos_operativos, 4),
        "egresos_tesoreria_usd": round(egresos, 4),
        "utilidad_estimada_usd": round(utilidad_estimada, 4),
        "cuentas_por_cobrar_pendiente_usd": round(cxc_pendiente, 4),
        "cuentas_por_pagar_pendiente_usd": round(cxp_pendiente, 4),
    }


def estado_resultados_dataframe(fecha_desde: str = "", fecha_hasta: str = "") -> pd.DataFrame:
    data = generar_estado_resultados(fecha_desde, fecha_hasta)
    filas = [
        ("Ventas", data["ventas_usd"]),
        ("Costo directo - materia prima", -data["compras_materia_prima_usd"]),
        ("Costo directo - reventa", -data["compras_reventa_usd"]),
        ("Utilidad bruta estimada", data["utilidad_bruta_usd"]),
        ("Gastos operativos - facturas", -data["gastos_factura_usd"]),
        ("Gastos operativos - manuales", -data["gastos_manual_usd"]),
        ("Gastos operativos - otros", -data["gastos_legacy_usd"]),
        ("Gastos operativos total", -data["gastos_operativos_usd"]),
        ("Utilidad neta estimada", data["utilidad_estimada_usd"]),
        ("Cuentas por cobrar pendientes", data["cuentas_por_cobrar_pendiente_usd"]),
        ("Cuentas por pagar pendientes", -data["cuentas_por_pagar_pendiente_usd"]),
    ]
    return pd.DataFrame(filas, columns=["Concepto", "Monto USD"])

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

BASE_DIR = Path(__file__).resolve().parents[1]
_QUERY_ERRORS: list[str] = []


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
    return row is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _pick(cols: set[str], *candidates: str) -> str | None:
    return next((candidate for candidate in candidates if candidate in cols), None)


def _record_error(context: str, exc: Exception) -> None:
    message = f"{context}: {type(exc).__name__}: {exc}"
    if message not in _QUERY_ERRORS:
        _QUERY_ERRORS.append(message)


def _scalar(conn: Any, sql: str, default: float = 0.0, context: str = "Métrica") -> float:
    try:
        row = conn.execute(sql).fetchone()
        return float((row[0] if row else default) or default)
    except Exception as exc:
        _record_error(context, exc)
        return default


def _count(conn: Any, sql: str, context: str = "Conteo") -> int:
    return int(_scalar(conn, sql, 0.0, context))


def _read_sql(conn: Any, sql: str, params: tuple[Any, ...] = (), context: str = "Consulta") -> pd.DataFrame:
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except Exception as exc:
        _record_error(context, exc)
        return pd.DataFrame()


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _read_csv(relative_path: str) -> pd.DataFrame:
    path = BASE_DIR / relative_path
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        try:
            return pd.read_csv(path, encoding="latin-1")
        except Exception as exc:
            _record_error(f"Lectura CSV {relative_path}", exc)
            return pd.DataFrame()


def _sum_csv(relative_path: str, column: str) -> float:
    df = _read_csv(relative_path)
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0).sum())


def _estado_count_csv(relative_path: str, column: str, values: set[str]) -> int:
    df = _read_csv(relative_path)
    if df.empty or column not in df.columns:
        return 0
    serie = df[column].fillna("").astype(str).str.strip().str.lower()
    return int(serie.isin(values).sum())


def _date_filter(column: str, start: date, end: date) -> str:
    return f"date({column}) BETWEEN date('{start.isoformat()}') AND date('{end.isoformat()}')"


def _active_filter(cols: set[str], alias: str = "") -> str:
    if "estado" not in cols:
        return "1=1"
    prefix = f"{alias}." if alias else ""
    return f"lower(COALESCE({prefix}estado,'activo')) NOT IN ('inactivo','eliminado','eliminada','anulado','anulada','cancelado','cancelada')"


def _collect_db_metrics(start: date, end: date) -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    today = date.today()
    days = max((end - start).days + 1, 1)

    with db_transaction() as conn:
        ventas_cols = _columns(conn, "ventas")
        if ventas_cols:
            total_col = _pick(ventas_cols, "total_usd", "total", "monto_usd", "monto") or "total"
            fecha_col = _pick(ventas_cols, "fecha", "fecha_venta", "created_at") or "fecha"
            valid_sales = _active_filter(ventas_cols)
            metrics["ventas_periodo"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE {_date_filter(fecha_col, start, end)} AND {valid_sales}", context="Ventas del periodo")
            metrics["ventas_hoy"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE {_date_filter(fecha_col, today, today)} AND {valid_sales}", context="Ventas de hoy")
            metrics["tickets_periodo"] = _count(conn, f"SELECT COUNT(*) FROM ventas WHERE {_date_filter(fecha_col, start, end)} AND {valid_sales}", context="Tickets del periodo")
            metrics["tickets_hoy"] = _count(conn, f"SELECT COUNT(*) FROM ventas WHERE {_date_filter(fecha_col, today, today)} AND {valid_sales}", context="Tickets de hoy")
            metrics["ventas_pendientes"] = _count(conn, "SELECT COUNT(*) FROM ventas WHERE lower(COALESCE(estado,'')) IN ('pendiente','por cobrar','credito','crédito')", context="Ventas pendientes") if "estado" in ventas_cols else 0
        else:
            metrics.update({"ventas_periodo": 0.0, "ventas_hoy": 0.0, "tickets_periodo": 0, "tickets_hoy": 0, "ventas_pendientes": 0})

        det_cols = _columns(conn, "ventas_detalle")
        if det_cols and {"cantidad", "costo_unitario_usd"}.issubset(det_cols):
            if "venta_id" in det_cols and ventas_cols:
                detail_date = "v.fecha"
                valid_detail = _active_filter(ventas_cols, "v")
                join = "JOIN ventas v ON v.id=d.venta_id"
            elif "fecha" in det_cols:
                detail_date = "d.fecha"
                valid_detail = _active_filter(det_cols, "d")
                join = ""
            else:
                detail_date = "NULL"
                valid_detail = "1=1"
                join = ""

            if detail_date != "NULL":
                base = f"FROM ventas_detalle d {join} WHERE {{period}} AND {valid_detail}"
                metrics["costo_ventas_periodo"] = _scalar(conn, f"SELECT COALESCE(SUM(d.cantidad*d.costo_unitario_usd),0) {base.format(period=_date_filter(detail_date, start, end))}", context="Costo de ventas del periodo")
                metrics["costo_ventas_hoy"] = _scalar(conn, f"SELECT COALESCE(SUM(d.cantidad*d.costo_unitario_usd),0) {base.format(period=_date_filter(detail_date, today, today))}", context="Costo de ventas de hoy")
                metrics["lineas_periodo"] = _count(conn, f"SELECT COUNT(*) {base.format(period=_date_filter(detail_date, start, end))}", context="Líneas del periodo")
                metrics["lineas_con_costo"] = _count(conn, f"SELECT COUNT(*) {base.format(period=_date_filter(detail_date, start, end))} AND COALESCE(d.costo_unitario_usd,0)>0", context="Líneas con costo")
                if {"precio_unitario_usd", "costo_unitario_usd"}.issubset(det_cols):
                    metrics["lineas_bajo_costo"] = _count(conn, f"SELECT COUNT(*) {base.format(period=_date_filter(detail_date, start, end))} AND COALESCE(d.precio_unitario_usd,0)<COALESCE(d.costo_unitario_usd,0) AND COALESCE(d.costo_unitario_usd,0)>0", context="Ventas bajo costo")
                else:
                    metrics["lineas_bajo_costo"] = 0
            else:
                metrics.update({"costo_ventas_periodo": 0.0, "costo_ventas_hoy": 0.0, "lineas_periodo": 0, "lineas_con_costo": 0, "lineas_bajo_costo": 0})
        else:
            metrics.update({"costo_ventas_periodo": 0.0, "costo_ventas_hoy": 0.0, "lineas_periodo": 0, "lineas_con_costo": 0, "lineas_bajo_costo": 0})

        gastos_cols = _columns(conn, "gastos")
        if gastos_cols:
            total_col = _pick(gastos_cols, "total_usd", "monto_usd", "total", "monto") or "total"
            fecha_col = _pick(gastos_cols, "fecha", "fecha_gasto", "created_at") or "fecha"
            valid_expenses = _active_filter(gastos_cols)
            metrics["gastos_periodo"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE {_date_filter(fecha_col, start, end)} AND {valid_expenses}", context="Gastos del periodo")
            metrics["gastos_hoy"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE {_date_filter(fecha_col, today, today)} AND {valid_expenses}", context="Gastos de hoy")
        else:
            metrics.update({"gastos_periodo": 0.0, "gastos_hoy": 0.0})

        inv_cols = _columns(conn, "inventario")
        if inv_cols:
            stock_col = _pick(inv_cols, "stock_actual", "cantidad", "stock", "existencia") or "stock_actual"
            minimo_col = _pick(inv_cols, "stock_minimo", "minimo", "stock_alerta")
            costo_col = _pick(inv_cols, "costo_unitario_usd", "costo_usd", "costo", "precio_compra_usd")
            precio_col = _pick(inv_cols, "precio_venta_usd", "precio_usd", "precio", "precio_publico_usd")
            active_inventory = _active_filter(inv_cols)
            metrics["productos_inventario"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE {active_inventory}", context="Productos activos")
            metrics["stock_critico"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE {active_inventory} AND COALESCE({stock_col},0)<=COALESCE({minimo_col},0)", context="Stock crítico") if minimo_col else 0
            metrics["valor_inventario"] = _scalar(conn, f"SELECT COALESCE(SUM(COALESCE({stock_col},0)*COALESCE({costo_col},0)),0) FROM inventario WHERE {active_inventory}", context="Valor inventario") if costo_col else 0.0
            metrics["productos_sin_costo"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE {active_inventory} AND COALESCE({costo_col},0)<=0", context="Productos sin costo") if costo_col else 0
            metrics["productos_sin_precio"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE {active_inventory} AND COALESCE({precio_col},0)<=0", context="Productos sin precio") if precio_col else 0
            metrics["productos_precio_bajo_costo"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE {active_inventory} AND COALESCE({precio_col},0)<=COALESCE({costo_col},0) AND COALESCE({costo_col},0)>0", context="Precio bajo costo") if costo_col and precio_col else 0
        else:
            metrics.update({"productos_inventario": 0, "stock_critico": 0, "valor_inventario": 0.0, "productos_sin_costo": 0, "productos_sin_precio": 0, "productos_precio_bajo_costo": 0})

        if _table_exists(conn, "cuentas_por_cobrar"):
            metrics["cxc_total"] = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd),0) FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) NOT IN ('pagada','cerrada','cancelada')", context="CxC total")
            metrics["cxc_vencida"] = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd),0) FROM cuentas_por_cobrar WHERE COALESCE(saldo_usd,0)>0 AND fecha_vencimiento IS NOT NULL AND date(fecha_vencimiento)<date('now','localtime')", context="CxC vencida")
        else:
            metrics.update({"cxc_total": 0.0, "cxc_vencida": 0.0})

        if _table_exists(conn, "cuentas_por_pagar_proveedores"):
            metrics["cxp_total"] = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd),0) FROM cuentas_por_pagar_proveedores WHERE lower(COALESCE(estado,'')) NOT IN ('pagada','cerrada','cancelada')", context="CxP total")
            metrics["cxp_vencida"] = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd),0) FROM cuentas_por_pagar_proveedores WHERE COALESCE(saldo_usd,0)>0 AND fecha_vencimiento IS NOT NULL AND date(fecha_vencimiento)<date('now','localtime')", context="CxP vencida")
        else:
            metrics.update({"cxp_total": 0.0, "cxp_vencida": 0.0})

        metrics["diferencia_caja_hoy"] = _scalar(conn, "SELECT COALESCE(SUM(diferencia_total_usd),0) FROM cierres_caja_turnos WHERE date(fecha_operativa)=date('now','localtime')", context="Diferencia de caja") if _table_exists(conn, "cierres_caja_turnos") and "diferencia_total_usd" in _columns(conn, "cierres_caja_turnos") else 0.0

    metrics["ganancia_bruta_periodo"] = float(metrics.get("ventas_periodo", 0)) - float(metrics.get("costo_ventas_periodo", 0))
    metrics["utilidad_periodo"] = float(metrics["ganancia_bruta_periodo"]) - float(metrics.get("gastos_periodo", 0))
    metrics["utilidad_hoy"] = float(metrics.get("ventas_hoy", 0)) - float(metrics.get("costo_ventas_hoy", 0)) - float(metrics.get("gastos_hoy", 0))
    metrics["margen_contribucion_pct"] = (float(metrics["ganancia_bruta_periodo"]) / float(metrics["ventas_periodo"]) * 100) if float(metrics.get("ventas_periodo", 0)) else 0.0
    metrics["margen_neto_pct"] = (float(metrics["utilidad_periodo"]) / float(metrics["ventas_periodo"]) * 100) if float(metrics.get("ventas_periodo", 0)) else 0.0
    metrics["ticket_promedio_hoy"] = float(metrics.get("ventas_hoy", 0)) / int(metrics.get("tickets_hoy", 0)) if int(metrics.get("tickets_hoy", 0)) else 0.0
    metrics["calidad_costos_pct"] = int(metrics.get("lineas_con_costo", 0)) / int(metrics.get("lineas_periodo", 0)) * 100 if int(metrics.get("lineas_periodo", 0)) else 0.0
    contribution_ratio = float(metrics.get("margen_contribucion_pct", 0)) / 100
    equilibrium_period = float(metrics.get("gastos_periodo", 0)) / contribution_ratio if contribution_ratio > 0 else 0.0
    metrics["punto_equilibrio_diario"] = equilibrium_period / days
    metrics["avance_equilibrio_hoy_pct"] = float(metrics.get("ventas_hoy", 0)) / float(metrics["punto_equilibrio_diario"]) * 100 if float(metrics.get("punto_equilibrio_diario", 0)) else 0.0
    metrics["posicion_neta_credito"] = float(metrics.get("cxc_total", 0)) - float(metrics.get("cxp_total", 0))
    return metrics


def _collect_csv_metrics() -> dict[str, float | int]:
    return {
        "reservas_almacen": _estado_count_csv("almacen/material_reservado_pedidos.csv", "estado_pedido", {"pendiente", "en produccion", "en producción", "reservado"}),
        "merma_almacen_usd": _sum_csv("almacen/mermas_almacen.csv", "costo_estimado"),
        "garantias_vencidas": _estado_count_csv("activos/garantias_activos.csv", "estado", {"vencida", "vencido", "expirada", "expirado"}),
        "documentos_activos_pendientes": _estado_count_csv("activos/documentos_activos.csv", "estado", {"pendiente", "faltante", "por subir"}),
        "bajas_pendientes": _estado_count_csv("activos/bajas_activos.csv", "estado", {"borrador", "pendiente", "por aprobar"}),
    }


def _sales_detail_source(conn: Any) -> tuple[str, str, str] | None:
    det_cols = _columns(conn, "ventas_detalle")
    ventas_cols = _columns(conn, "ventas")
    if "venta_id" in det_cols and ventas_cols:
        return "ventas_detalle d JOIN ventas v ON v.id=d.venta_id", "v.fecha", _active_filter(ventas_cols, "v")
    if "fecha" in det_cols:
        return "ventas_detalle d", "d.fecha", _active_filter(det_cols, "d")
    return None


def _ventas_tendencia_df(start: date, end: date) -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas")
        total = _pick(cols, "total_usd", "total", "monto_usd", "monto")
        fecha = _pick(cols, "fecha", "fecha_venta", "created_at")
        if not total or not fecha:
            return pd.DataFrame()
        return _read_sql(conn, f"SELECT date({fecha}) AS fecha, COALESCE(SUM({total}),0) AS ventas_usd FROM ventas WHERE {_date_filter(fecha, start, end)} AND {_active_filter(cols)} GROUP BY date({fecha}) ORDER BY fecha", context="Tendencia de ventas")


def _ventas_por_linea_df(start: date, end: date) -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas_detalle")
        source = _sales_detail_source(conn)
        if source and {"descripcion", "cantidad", "subtotal_usd"}.issubset(cols):
            table, fecha, valid = source
            return _read_sql(conn, f"SELECT d.descripcion AS linea, SUM(d.cantidad) AS unidades, COUNT(*) AS operaciones, COALESCE(SUM(d.subtotal_usd),0) AS ventas_usd FROM {table} WHERE {_date_filter(fecha, start, end)} AND {valid} GROUP BY d.descripcion ORDER BY ventas_usd DESC LIMIT 12", context="Ventas por línea")
    return pd.DataFrame()


def _top_rentabilidad_df(start: date, end: date) -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas_detalle")
        source = _sales_detail_source(conn)
        required = {"descripcion", "cantidad", "costo_unitario_usd", "subtotal_usd"}
        if source and required.issubset(cols):
            table, fecha, valid = source
            return _read_sql(conn, f"SELECT d.descripcion AS item, SUM(d.cantidad) AS unidades, COALESCE(SUM(d.subtotal_usd),0) AS ingreso_usd, COALESCE(SUM(d.cantidad*d.costo_unitario_usd),0) AS costo_usd, COALESCE(SUM(d.subtotal_usd-(d.cantidad*d.costo_unitario_usd)),0) AS ganancia_usd FROM {table} WHERE {_date_filter(fecha, start, end)} AND {valid} GROUP BY d.descripcion ORDER BY ganancia_usd DESC LIMIT 10", context="Top rentabilidad")
    return pd.DataFrame()


def _ventas_bajo_costo_df(start: date, end: date) -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas_detalle")
        source = _sales_detail_source(conn)
        if source and {"descripcion", "cantidad", "precio_unitario_usd", "costo_unitario_usd"}.issubset(cols):
            table, fecha, valid = source
            return _read_sql(conn, f"SELECT {fecha} AS fecha, d.descripcion, d.cantidad, d.precio_unitario_usd, d.costo_unitario_usd, (d.precio_unitario_usd-d.costo_unitario_usd) AS diferencia_unitaria_usd FROM {table} WHERE {_date_filter(fecha, start, end)} AND {valid} AND COALESCE(d.precio_unitario_usd,0)<COALESCE(d.costo_unitario_usd,0) AND COALESCE(d.costo_unitario_usd,0)>0 ORDER BY {fecha} DESC LIMIT 100", context="Detalle bajo costo")
    return pd.DataFrame()


def _inventario_familia_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        familia = _pick(cols, "familia", "categoria", "tipo", "linea")
        stock = _pick(cols, "stock_actual", "cantidad", "stock", "existencia")
        minimo = _pick(cols, "stock_minimo", "minimo", "stock_alerta")
        costo = _pick(cols, "costo_unitario_usd", "costo_usd", "costo", "precio_compra_usd")
        if not familia or not stock:
            return pd.DataFrame()
        valor = f"SUM(COALESCE({stock},0)*COALESCE({costo},0))" if costo else "0"
        critico = f"SUM(CASE WHEN COALESCE({stock},0)<=COALESCE({minimo},0) THEN 1 ELSE 0 END)" if minimo else "0"
        return _read_sql(conn, f"SELECT COALESCE({familia},'Sin familia') AS familia, COUNT(*) AS productos, COALESCE(SUM({stock}),0) AS unidades, COALESCE({critico},0) AS criticos, COALESCE({valor},0) AS valor_usd FROM inventario WHERE {_active_filter(cols)} GROUP BY COALESCE({familia},'Sin familia') ORDER BY criticos DESC, valor_usd DESC LIMIT 15", context="Inventario por familia")


def _inventario_riesgos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        if not {"nombre", "costo_unitario_usd", "precio_venta_usd", "stock_minimo", "categoria"}.issubset(cols):
            return pd.DataFrame()
        return _read_sql(conn, f"""SELECT sku,nombre,categoria,stock_actual,stock_minimo,costo_unitario_usd,precio_venta_usd,
        CASE WHEN COALESCE(costo_unitario_usd,0)<=0 THEN 'Sin costo' WHEN COALESCE(precio_venta_usd,0)<=0 THEN 'Sin precio'
        WHEN COALESCE(precio_venta_usd,0)<=COALESCE(costo_unitario_usd,0) THEN 'Precio bajo o igual al costo'
        WHEN COALESCE(stock_minimo,0)<=0 THEN 'Sin mínimo definido' WHEN COALESCE(categoria,'')='' THEN 'Sin categoría' ELSE 'OK' END AS riesgo
        FROM inventario WHERE {_active_filter(cols)} AND (COALESCE(costo_unitario_usd,0)<=0 OR COALESCE(precio_venta_usd,0)<=0 OR COALESCE(precio_venta_usd,0)<=COALESCE(costo_unitario_usd,0) OR COALESCE(stock_minimo,0)<=0 OR COALESCE(categoria,'')='') ORDER BY riesgo,nombre LIMIT 200""", context="Riesgos de inventario")


def _compras_sugeridas_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        required = {"sku", "nombre", "categoria", "stock_actual", "stock_minimo", "costo_unitario_usd"}
        if not required.issubset(cols):
            return pd.DataFrame()
        target = "COALESCE(stock_ideal,stock_minimo)" if "stock_ideal" in cols else "stock_minimo"
        trigger = "COALESCE(punto_reorden,stock_minimo)" if "punto_reorden" in cols else "stock_minimo"
        lead = "lead_time_dias" if "lead_time_dias" in cols else "0 AS lead_time_dias"
        return _read_sql(conn, f"SELECT sku,nombre,categoria,stock_actual,stock_minimo,{lead},MAX({target}-stock_actual,0) AS cantidad_sugerida,costo_unitario_usd,MAX({target}-stock_actual,0)*costo_unitario_usd AS inversion_estimada_usd FROM inventario WHERE {_active_filter(cols)} AND COALESCE(stock_actual,0)<=COALESCE({trigger},0) ORDER BY inversion_estimada_usd DESC,nombre LIMIT 100", context="Compras sugeridas")


def _cxc_vencida_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _columns(conn, "cuentas_por_cobrar"):
            return pd.DataFrame()
        return _read_sql(conn, "SELECT cxc.id,cl.nombre AS cliente,cxc.estado,cxc.monto_original_usd,cxc.monto_cobrado_usd,cxc.saldo_usd,cxc.fecha_vencimiento,CAST(julianday(date('now','localtime'))-julianday(date(cxc.fecha_vencimiento)) AS INTEGER) AS dias_vencida FROM cuentas_por_cobrar cxc LEFT JOIN clientes cl ON cl.id=cxc.cliente_id WHERE COALESCE(cxc.saldo_usd,0)>0 AND cxc.fecha_vencimiento IS NOT NULL AND date(cxc.fecha_vencimiento)<date('now','localtime') ORDER BY date(cxc.fecha_vencimiento) LIMIT 100", context="CxC vencida")


def _cxp_vencida_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _columns(conn, "cuentas_por_pagar_proveedores"):
            return pd.DataFrame()
        return _read_sql(conn, "SELECT cxp.id,p.nombre AS proveedor,cxp.estado,cxp.monto_original_usd,cxp.monto_pagado_usd,cxp.saldo_usd,cxp.fecha_vencimiento,CAST(julianday(date('now','localtime'))-julianday(date(cxp.fecha_vencimiento)) AS INTEGER) AS dias_vencida FROM cuentas_por_pagar_proveedores cxp LEFT JOIN proveedores p ON p.id=cxp.proveedor_id WHERE COALESCE(cxp.saldo_usd,0)>0 AND cxp.fecha_vencimiento IS NOT NULL AND date(cxp.fecha_vencimiento)<date('now','localtime') ORDER BY date(cxp.fecha_vencimiento) LIMIT 100", context="CxP vencida")


def _caja_metodos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas")
        if {"metodo_pago", "total_usd", "fecha"}.issubset(cols):
            return _read_sql(conn, f"SELECT metodo_pago,COUNT(*) AS operaciones,COALESCE(SUM(total_usd),0) AS total_usd FROM ventas WHERE date(fecha)=date('now','localtime') AND {_active_filter(cols)} GROUP BY metodo_pago ORDER BY total_usd DESC", context="Caja por método")
    return pd.DataFrame()


def _produccion_estado_df() -> pd.DataFrame:
    candidates = [("ordenes_produccion", "estado"), ("planificacion_produccion", "estado"), ("despachos_entregas", "estado"), ("cola_impresion", "estado")]
    with db_transaction() as conn:
        for table, estado in candidates:
            if estado in _columns(conn, table):
                return _read_sql(conn, f"SELECT '{table}' AS fuente,COALESCE({estado},'Sin estado') AS estado,COUNT(*) AS cantidad FROM {table} GROUP BY COALESCE({estado},'Sin estado') ORDER BY cantidad DESC LIMIT 12", context="Producción por estado")
    return pd.DataFrame()


def _datos_minimos_df() -> pd.DataFrame:
    rows = [("Inventario","sku","Código único","BOND-CARTA-001","Evita duplicados."),("Inventario","categoria","Familia","Papel / Tinta / Papelería","Analiza rentabilidad."),("Inventario","stock_actual","Existencia","50","Controla stock."),("Inventario","stock_minimo","Mínimo","10","Activa compras."),("Inventario","stock_ideal","Objetivo de reposición","50","Mejora compras sugeridas."),("Inventario","costo_unitario_usd","Costo real","0.018","Evita pérdidas."),("Inventario","precio_venta_usd","Precio venta","0.05","Calcula margen."),("Venta detalle","cantidad","Cantidad","4","Costo/ganancia."),("Venta detalle","precio_unitario_usd","Precio cobrado","0.50","Detecta barato."),("Venta detalle","costo_unitario_usd","Costo unitario","0.22","Calcula utilidad real."),("Venta","metodo_pago","Forma de pago","efectivo / pago móvil","Cuadra caja."),("CxC/CxP","saldo_usd","Saldo pendiente","3.00","Controla liquidez."),("CxC/CxP","fecha_vencimiento","Fecha límite","2026-06-30","Detecta vencidas.")]
    return pd.DataFrame(rows, columns=["Módulo", "Campo", "Qué llenar", "Ejemplo", "Para qué sirve"])


def _plantilla_inventario_df() -> pd.DataFrame:
    return pd.DataFrame([{"sku":"BOND-CARTA-001","nombre":"Papel bond carta 75g","categoria":"Papel","unidad":"hoja","stock_actual":500,"stock_minimo":100,"stock_ideal":500,"costo_unitario_usd":0.018,"precio_venta_usd":0.05}])


def _plantilla_ventas_detalle_df() -> pd.DataFrame:
    return pd.DataFrame([{"fecha":date.today().isoformat(),"descripcion":"Impresión B/N carta","cantidad":1,"precio_unitario_usd":0.25,"costo_unitario_usd":0.08,"subtotal_usd":0.25}])


def _build_alerts(metrics: dict[str, float | int]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    if _QUERY_ERRORS:
        alerts.append({"nivel":"Crítica","área":"Sistema","alerta":f"Hay {len(_QUERY_ERRORS)} cálculo(s) que no pudieron completarse.","acción":"Revisar el detalle técnico antes de confiar en valores en cero."})
    if int(metrics.get("lineas_bajo_costo", 0)):
        alerts.append({"nivel":"Crítica","área":"Precios","alerta":f"Hay {int(metrics['lineas_bajo_costo'])} línea(s) vendidas bajo costo en el periodo.","acción":"Corregir precio, costo y tasa."})
    if float(metrics.get("calidad_costos_pct", 0)) < 95 and int(metrics.get("lineas_periodo", 0)):
        alerts.append({"nivel":"Media","área":"Datos","alerta":f"Solo {float(metrics['calidad_costos_pct']):.1f}% de las líneas tiene costo válido.","acción":"Completar costos; la utilidad es provisional."})
    if int(metrics.get("productos_precio_bajo_costo", 0)):
        alerts.append({"nivel":"Crítica","área":"Inventario","alerta":f"Hay {int(metrics['productos_precio_bajo_costo'])} producto(s) con precio igual o menor al costo.","acción":"Actualizar precios o costos."})
    if float(metrics.get("cxc_vencida", 0)):
        alerts.append({"nivel":"Crítica","área":"Cobranza","alerta":f"Hay ${float(metrics['cxc_vencida']):,.2f} vencidos por cobrar.","acción":"Gestionar cobro y limitar nuevo crédito."})
    if float(metrics.get("cxp_vencida", 0)):
        alerts.append({"nivel":"Crítica","área":"Proveedores","alerta":f"Hay ${float(metrics['cxp_vencida']):,.2f} vencidos por pagar.","acción":"Priorizar pagos y negociar fechas."})
    if int(metrics.get("stock_critico", 0)):
        alerts.append({"nivel":"Crítica","área":"Inventario","alerta":f"Hay {int(metrics['stock_critico'])} producto(s) en o bajo mínimo.","acción":"Revisar compras sugeridas."})
    if abs(float(metrics.get("diferencia_caja_hoy", 0))) > 0.009:
        alerts.append({"nivel":"Crítica","área":"Caja","alerta":f"Diferencia de caja hoy: ${float(metrics['diferencia_caja_hoy']):,.2f}.","acción":"Cuadrar métodos de pago antes de cerrar."})
    if float(metrics.get("utilidad_periodo", 0)) < 0:
        alerts.append({"nivel":"Crítica","área":"Finanzas","alerta":"La utilidad estimada del periodo es negativa.","acción":"Revisar costos, gastos y precios."})
    return alerts


def _recommended_actions_df(metrics: dict[str, float | int]) -> pd.DataFrame:
    rows = [("Alta","Precios","Ventas bajo costo y productos con margen insuficiente.","Corregir precio, costo y tasa.","Evitar pérdidas."),("Alta","Cobranza y pagos","CxC y CxP vencidas.","Cobrar primero y calendarizar pagos.","Proteger caja."),("Alta","Inventario","Stock crítico y reposición.","Comprar según stock ideal y punto de reorden.","Evitar ventas bloqueadas."),("Media","Datos","Cobertura de costos por debajo de 95%.","Completar costo unitario en ventas.","Utilidad confiable."),("Media","Caja","Métodos de pago y diferencia de cierre.","Cuadrar diariamente.","Caja limpia."),("Media","Rentabilidad","Margen y punto de equilibrio.","Ajustar precios o reducir gastos.","Proteger utilidad.")]
    return pd.DataFrame(rows, columns=["Prioridad", "Área", "Revisar", "Acción recomendada", "Decisión esperada"])


def _show_df_or_info(df: pd.DataFrame, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def _resolve_period() -> tuple[str, date, date]:
    today = date.today()
    option = st.selectbox("Periodo de análisis", ["Hoy", "Últimos 7 días", "Mes actual", "Mes anterior", "Personalizado"], index=2)
    if option == "Hoy":
        return option, today, today
    if option == "Últimos 7 días":
        return option, today - timedelta(days=6), today
    if option == "Mes anterior":
        first_current = today.replace(day=1)
        end = first_current - timedelta(days=1)
        return option, end.replace(day=1), end
    if option == "Personalizado":
        c1, c2 = st.columns(2)
        start = c1.date_input("Desde", today.replace(day=1), key="panel_period_start")
        end = c2.date_input("Hasta", today, key="panel_period_end")
        if start > end:
            st.warning("La fecha inicial era mayor que la final; se intercambiaron automáticamente.")
            start, end = end, start
        return option, start, end
    return option, today.replace(day=1), today


def render_panel_ejecutivo(usuario: str = "Sistema", context_key: str = "principal") -> None:
    _QUERY_ERRORS.clear()
    st.title("📊 Panel ejecutivo")
    st.caption(f"Centro de control financiero, operativo y comercial · {date.today().isoformat()} · Usuario: {usuario}")
    instance_key = f"panel_ejecutivo_{context_key}_{abs(hash(str(usuario))) % 100000}"

    period_label, start, end = _resolve_period()
    st.caption(f"Analizando: {period_label} · {start.isoformat()} a {end.isoformat()}")
    metrics = {**_collect_db_metrics(start, end), **_collect_csv_metrics()}

    st.subheader("🌅 Pulso de hoy")
    h1, h2, h3, h4, h5, h6 = st.columns(6)
    h1.metric("Ventas hoy", f"${float(metrics.get('ventas_hoy',0)):,.2f}")
    h2.metric("Costo vendido hoy", f"${float(metrics.get('costo_ventas_hoy',0)):,.2f}")
    h3.metric("Gastos hoy", f"${float(metrics.get('gastos_hoy',0)):,.2f}")
    h4.metric("Utilidad real hoy", f"${float(metrics.get('utilidad_hoy',0)):,.2f}")
    h5.metric("Tickets hoy", int(metrics.get("tickets_hoy",0)))
    h6.metric("Ticket promedio", f"${float(metrics.get('ticket_promedio_hoy',0)):,.2f}")

    st.subheader(f"💼 Salud financiera · {period_label}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ventas", f"${float(metrics.get('ventas_periodo',0)):,.2f}")
    c2.metric("Costo de ventas", f"${float(metrics.get('costo_ventas_periodo',0)):,.2f}")
    c3.metric("Gastos", f"${float(metrics.get('gastos_periodo',0)):,.2f}")
    c4.metric("Ganancia bruta", f"${float(metrics.get('ganancia_bruta_periodo',0)):,.2f}", f"{float(metrics.get('margen_contribucion_pct',0)):.1f}%")
    c5.metric("Utilidad estimada", f"${float(metrics.get('utilidad_periodo',0)):,.2f}", f"{float(metrics.get('margen_neto_pct',0)):.1f}%")

    q1, q2, q3, q4 = st.columns(4)
    q1.metric("Cobertura de costos", f"{float(metrics.get('calidad_costos_pct',0)):.1f}%")
    q2.metric("Equilibrio diario estimado", f"${float(metrics.get('punto_equilibrio_diario',0)):,.2f}")
    q3.metric("Avance hoy", f"{float(metrics.get('avance_equilibrio_hoy_pct',0)):,.1f}%")
    q4.metric("Posición neta crédito", f"${float(metrics.get('posicion_neta_credito',0)):,.2f}")
    if int(metrics.get("lineas_periodo",0)) and float(metrics.get("calidad_costos_pct",0)) < 95:
        st.warning("La utilidad del periodo es provisional porque faltan costos en algunas líneas de venta.")

    r1, r2, r3, r4 = st.columns(4)
    r1.metric("CxC total", f"${float(metrics.get('cxc_total',0)):,.2f}")
    r2.metric("CxC vencida", f"${float(metrics.get('cxc_vencida',0)):,.2f}")
    r3.metric("CxP total", f"${float(metrics.get('cxp_total',0)):,.2f}")
    r4.metric("CxP vencida", f"${float(metrics.get('cxp_vencida',0)):,.2f}")

    st.subheader("📦 Operación, inventario y riesgos")
    o1, o2, o3, o4, o5 = st.columns(5)
    o1.metric("Valor inventario activo", f"${float(metrics.get('valor_inventario',0)):,.2f}")
    o2.metric("Stock crítico", int(metrics.get("stock_critico",0)))
    o3.metric("Ventas bajo costo", int(metrics.get("lineas_bajo_costo",0)))
    o4.metric("Precio ≤ costo", int(metrics.get("productos_precio_bajo_costo",0)))
    o5.metric("Diferencia caja hoy", f"${float(metrics.get('diferencia_caja_hoy',0)):,.2f}")

    st.divider()
    alerts = _build_alerts(metrics)
    st.subheader("🚨 Centro de alertas gerenciales")
    if alerts:
        st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
    else:
        st.success("No hay alertas gerenciales críticas con la información disponible.")
    if _QUERY_ERRORS:
        with st.expander("Detalle técnico de cálculos no completados"):
            for error in _QUERY_ERRORS:
                st.code(error)

    tabs = st.tabs(["📈 Ventas", "💸 Bajo costo", "📦 Inventario", "🛒 Compras", "💳 CxC", "🧾 CxP", "🏦 Caja", "🏭 Producción", "🧾 Datos mínimos", "📌 Acciones"])
    with tabs[0]:
        trend = _ventas_tendencia_df(start, end)
        if not trend.empty:
            st.line_chart(trend.set_index("fecha")["ventas_usd"])
        _show_df_or_info(_ventas_por_linea_df(start, end), "No hay ventas detalladas suficientes para agrupar en el periodo.")
        st.markdown("#### Top rentabilidad del periodo")
        _show_df_or_info(_top_rentabilidad_df(start, end), "No hay datos suficientes de costo y ganancia en el periodo.")
    with tabs[1]:
        _show_df_or_info(_ventas_bajo_costo_df(start, end), "No hay ventas bajo costo en el periodo seleccionado.")
    with tabs[2]:
        st.markdown("#### Inventario activo por familia")
        _show_df_or_info(_inventario_familia_df(), "No hay datos suficientes para agrupar inventario.")
        st.markdown("#### Riesgos de datos y precios")
        _show_df_or_info(_inventario_riesgos_df(), "No hay productos activos con datos incompletos o precio bajo costo.")
    with tabs[3]:
        _show_df_or_info(_compras_sugeridas_df(), "No hay compras sugeridas por punto de reorden o stock mínimo.")
    with tabs[4]:
        _show_df_or_info(_cxc_vencida_df(), "No hay cuentas por cobrar vencidas.")
    with tabs[5]:
        _show_df_or_info(_cxp_vencida_df(), "No hay cuentas por pagar vencidas.")
    with tabs[6]:
        _show_df_or_info(_caja_metodos_df(), "No hay ventas de hoy separadas por método de pago.")
    with tabs[7]:
        _show_df_or_info(_produccion_estado_df(), "No hay órdenes o estados de producción suficientes.")
    with tabs[8]:
        st.caption("Completa estos campos para que el ERP calcule caja, margen, compras y crédito sin adivinar.")
        st.dataframe(_datos_minimos_df(), use_container_width=True, hide_index=True)
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button("⬇️ Plantilla inventario CSV", data=_csv_bytes(_plantilla_inventario_df()), file_name="plantilla_inventario_copy_mary.csv", mime="text/csv", use_container_width=True, key=f"{instance_key}_plantilla_inventario_csv")
        with col_b:
            st.download_button("⬇️ Plantilla ventas detalle CSV", data=_csv_bytes(_plantilla_ventas_detalle_df()), file_name="plantilla_ventas_detalle_copy_mary.csv", mime="text/csv", use_container_width=True, key=f"{instance_key}_plantilla_ventas_detalle_csv")
    with tabs[9]:
        st.dataframe(_recommended_actions_df(metrics), use_container_width=True, hide_index=True)

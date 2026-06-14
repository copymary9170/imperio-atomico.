from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

BASE_DIR = Path(__file__).resolve().parents[1]


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _columns(conn: Any, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _pick(cols: set[str], *candidates: str) -> str | None:
    for candidate in candidates:
        if candidate in cols:
            return candidate
    return None


def _scalar(conn: Any, sql: str, default: float = 0.0) -> float:
    try:
        row = conn.execute(sql).fetchone()
        if row is None:
            return default
        value = row[0]
        return float(value or default)
    except Exception:
        return default


def _count(conn: Any, sql: str) -> int:
    return int(_scalar(conn, sql, 0.0))


def _read_sql(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except Exception:
        return pd.DataFrame()


def _read_csv(relative_path: str) -> pd.DataFrame:
    path = BASE_DIR / relative_path
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        try:
            return pd.read_csv(path, encoding="latin-1")
        except Exception:
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


def _collect_db_metrics() -> dict[str, float | int]:
    metrics: dict[str, float | int] = {}
    with db_transaction() as conn:
        ventas_cols = _columns(conn, "ventas")
        if ventas_cols:
            total_col = _pick(ventas_cols, "total_usd", "total", "monto_usd", "monto") or "total"
            costo_col = _pick(ventas_cols, "costo_total_usd", "costo_usd", "costo", "costo_total")
            ganancia_col = _pick(ventas_cols, "ganancia_usd", "utilidad_usd", "margen_usd", "beneficio_usd")
            fecha_col = _pick(ventas_cols, "fecha", "fecha_venta", "created_at") or "fecha"
            estado_filter = "AND lower(COALESCE(estado,'')) NOT IN ('anulada','anulado','cancelada','cancelado')" if "estado" in ventas_cols else ""

            metrics["ventas_mes"] = _scalar(
                conn,
                f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}",
            )
            metrics["ventas_hoy"] = _scalar(
                conn,
                f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE date({fecha_col})=date('now') {estado_filter}",
            )
            metrics["ventas_7d"] = _scalar(
                conn,
                f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE date({fecha_col})>=date('now','-6 day') {estado_filter}",
            )
            metrics["tickets_hoy"] = _count(
                conn,
                f"SELECT COUNT(*) FROM ventas WHERE date({fecha_col})=date('now') {estado_filter}",
            )
            metrics["ventas_pendientes"] = _count(
                conn,
                "SELECT COUNT(*) FROM ventas WHERE lower(COALESCE(estado,'')) IN ('pendiente','por cobrar','credito','crédito')" if "estado" in ventas_cols else "SELECT 0",
            )
            if costo_col:
                metrics["costo_ventas_mes"] = _scalar(
                    conn,
                    f"SELECT COALESCE(SUM({costo_col}),0) FROM ventas WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}",
                )
            elif ganancia_col:
                ganancia_mes = _scalar(conn, f"SELECT COALESCE(SUM({ganancia_col}),0) FROM ventas WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}")
                metrics["costo_ventas_mes"] = max(0.0, float(metrics["ventas_mes"]) - ganancia_mes)
            else:
                metrics["costo_ventas_mes"] = 0.0
        else:
            metrics.update({"ventas_mes": 0.0, "ventas_hoy": 0.0, "ventas_7d": 0.0, "tickets_hoy": 0, "ventas_pendientes": 0, "costo_ventas_mes": 0.0})

        gastos_cols = _columns(conn, "gastos")
        if gastos_cols:
            total_col = _pick(gastos_cols, "total_usd", "monto_usd", "total", "monto") or "total"
            fecha_col = _pick(gastos_cols, "fecha", "fecha_gasto", "created_at") or "fecha"
            estado_filter = "AND lower(COALESCE(estado,'')) NOT IN ('anulado','anulada','cancelado','cancelada')" if "estado" in gastos_cols else ""
            metrics["gastos_mes"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}")
            metrics["gastos_hoy"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE date({fecha_col})=date('now') {estado_filter}")
        else:
            metrics["gastos_mes"] = 0.0
            metrics["gastos_hoy"] = 0.0

        inventario_cols = _columns(conn, "inventario")
        if inventario_cols:
            stock_col = _pick(inventario_cols, "stock_actual", "cantidad", "stock", "existencia") or "stock"
            minimo_col = _pick(inventario_cols, "stock_minimo", "minimo", "stock_alerta")
            costo_col = _pick(inventario_cols, "costo_unitario_usd", "costo_usd", "costo", "precio_compra_usd")
            metrics["productos_inventario"] = _count(conn, "SELECT COUNT(*) FROM inventario")
            metrics["stock_critico"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE COALESCE({stock_col},0) <= COALESCE({minimo_col},0)") if minimo_col else 0
            metrics["valor_inventario"] = _scalar(conn, f"SELECT COALESCE(SUM(COALESCE({stock_col},0) * COALESCE({costo_col},0)),0) FROM inventario") if costo_col else 0.0
        else:
            metrics.update({"productos_inventario": 0, "stock_critico": 0, "valor_inventario": 0.0})

        activos_cols = _columns(conn, "activos")
        if activos_cols:
            metrics["activos"] = _count(conn, "SELECT COUNT(*) FROM activos WHERE COALESCE(activo,1)=1") if "activo" in activos_cols else _count(conn, "SELECT COUNT(*) FROM activos")
            metrics["valor_activos"] = _scalar(conn, "SELECT COALESCE(SUM(inversion),0) FROM activos WHERE COALESCE(activo,1)=1") if "inversion" in activos_cols else 0.0
        else:
            metrics["activos"] = 0
            metrics["valor_activos"] = 0.0

        rutas_cols = _columns(conn, "rutas_produccion")
        metrics["rutas_activas"] = _count(conn, "SELECT COUNT(*) FROM rutas_produccion WHERE lower(COALESCE(estado,''))='activa'") if rutas_cols else 0
        metrics["mantenimiento_abierto"] = _count(conn, "SELECT COUNT(*) FROM industrial_maintenance_orders WHERE estado IN ('pendiente','programado','en_ejecucion')") if _table_exists(conn, "industrial_maintenance_orders") else 0

        if _table_exists(conn, "cierres_caja_turnos"):
            cierre_cols = _columns(conn, "cierres_caja_turnos")
            fecha_col = _pick(cierre_cols, "fecha_operativa", "fecha", "created_at") or "fecha_operativa"
            metrics["cierres_diferencia_hoy"] = _count(conn, f"SELECT COUNT(*) FROM cierres_caja_turnos WHERE date({fecha_col})=date('now') AND estado='Con diferencia'") if "estado" in cierre_cols else 0
            metrics["diferencia_caja_hoy"] = _scalar(conn, f"SELECT COALESCE(SUM(diferencia_total_usd),0) FROM cierres_caja_turnos WHERE date({fecha_col})=date('now')") if "diferencia_total_usd" in cierre_cols else 0.0
        else:
            metrics["cierres_diferencia_hoy"] = 0
            metrics["diferencia_caja_hoy"] = 0.0

    metrics["ganancia_bruta_mes"] = float(metrics.get("ventas_mes", 0.0)) - float(metrics.get("costo_ventas_mes", 0.0))
    metrics["utilidad_estimada_mes"] = float(metrics.get("ganancia_bruta_mes", 0.0)) - float(metrics.get("gastos_mes", 0.0))
    metrics["utilidad_estimada_hoy"] = float(metrics.get("ventas_hoy", 0.0)) - float(metrics.get("gastos_hoy", 0.0))
    metrics["margen_bruto_pct"] = (float(metrics["ganancia_bruta_mes"]) / float(metrics["ventas_mes"]) * 100) if float(metrics.get("ventas_mes", 0.0)) else 0.0
    metrics["margen_neto_pct"] = (float(metrics["utilidad_estimada_mes"]) / float(metrics["ventas_mes"]) * 100) if float(metrics.get("ventas_mes", 0.0)) else 0.0
    metrics["venta_promedio_hoy"] = (float(metrics["ventas_hoy"]) / int(metrics["tickets_hoy"])) if int(metrics.get("tickets_hoy", 0)) else 0.0
    metrics["punto_equilibrio_diario"] = float(metrics.get("gastos_mes", 0.0)) / max(date.today().day, 1)
    metrics["avance_equilibrio_hoy_pct"] = (float(metrics.get("ventas_hoy", 0.0)) / float(metrics["punto_equilibrio_diario"]) * 100) if float(metrics.get("punto_equilibrio_diario", 0.0)) else 0.0
    return metrics


def _collect_csv_metrics() -> dict[str, float | int]:
    return {
        "reservas_almacen": _estado_count_csv("almacen/material_reservado_pedidos.csv", "estado_pedido", {"pendiente", "en produccion", "en producción", "reservado"}),
        "merma_almacen_usd": _sum_csv("almacen/mermas_almacen.csv", "costo_estimado"),
        "garantias_vencidas": _estado_count_csv("activos/garantias_activos.csv", "estado", {"vencida", "vencido", "expirada", "expirado"}),
        "documentos_activos_pendientes": _estado_count_csv("activos/documentos_activos.csv", "estado", {"pendiente", "faltante", "por subir"}),
        "bajas_pendientes": _estado_count_csv("activos/bajas_activos.csv", "estado", {"borrador", "pendiente", "por aprobar"}),
    }


def _ventas_por_linea_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas")
        if not cols:
            return pd.DataFrame()
        total_col = _pick(cols, "total_usd", "total", "monto_usd", "monto")
        fecha_col = _pick(cols, "fecha", "fecha_venta", "created_at")
        linea_col = _pick(cols, "linea_negocio", "categoria", "tipo_servicio", "tipo", "area")
        if not total_col or not fecha_col or not linea_col:
            return pd.DataFrame()
        estado_filter = "AND lower(COALESCE(estado,'')) NOT IN ('anulada','anulado','cancelada','cancelado')" if "estado" in cols else ""
        return _read_sql(
            conn,
            f"""
            SELECT COALESCE({linea_col}, 'Sin clasificar') AS linea,
                   COUNT(*) AS operaciones,
                   COALESCE(SUM({total_col}),0) AS ventas_usd
            FROM ventas
            WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}
            GROUP BY COALESCE({linea_col}, 'Sin clasificar')
            ORDER BY ventas_usd DESC
            LIMIT 12
            """,
        )


def _inventario_familia_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        if not cols:
            return pd.DataFrame()
        familia_col = _pick(cols, "familia", "categoria", "tipo", "linea")
        stock_col = _pick(cols, "stock_actual", "cantidad", "stock", "existencia")
        minimo_col = _pick(cols, "stock_minimo", "minimo", "stock_alerta")
        costo_col = _pick(cols, "costo_unitario_usd", "costo_usd", "costo", "precio_compra_usd")
        if not familia_col or not stock_col:
            return pd.DataFrame()
        valor_expr = f"SUM(COALESCE({stock_col},0) * COALESCE({costo_col},0))" if costo_col else "0"
        critico_expr = f"SUM(CASE WHEN COALESCE({stock_col},0) <= COALESCE({minimo_col},0) THEN 1 ELSE 0 END)" if minimo_col else "0"
        return _read_sql(
            conn,
            f"""
            SELECT COALESCE({familia_col}, 'Sin familia') AS familia,
                   COUNT(*) AS productos,
                   COALESCE(SUM({stock_col}),0) AS unidades,
                   COALESCE({critico_expr},0) AS criticos,
                   COALESCE({valor_expr},0) AS valor_usd
            FROM inventario
            GROUP BY COALESCE({familia_col}, 'Sin familia')
            ORDER BY criticos DESC, valor_usd DESC
            LIMIT 15
            """,
        )


def _produccion_estado_df() -> pd.DataFrame:
    candidates = [
        ("ordenes_produccion", "estado"),
        ("planificacion_produccion", "estado"),
        ("despachos_entregas", "estado"),
        ("cola_impresion", "estado"),
    ]
    with db_transaction() as conn:
        for table, estado_col in candidates:
            cols = _columns(conn, table)
            if estado_col in cols:
                return _read_sql(
                    conn,
                    f"""
                    SELECT '{table}' AS fuente,
                           COALESCE({estado_col}, 'Sin estado') AS estado,
                           COUNT(*) AS cantidad
                    FROM {table}
                    GROUP BY COALESCE({estado_col}, 'Sin estado')
                    ORDER BY cantidad DESC
                    LIMIT 12
                    """,
                )
    return pd.DataFrame()


def _top_rentabilidad_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "ventas")
        if not cols:
            return pd.DataFrame()
        nombre_col = _pick(cols, "producto", "servicio", "descripcion", "concepto", "detalle")
        total_col = _pick(cols, "total_usd", "total", "monto_usd", "monto")
        costo_col = _pick(cols, "costo_total_usd", "costo_usd", "costo", "costo_total")
        ganancia_col = _pick(cols, "ganancia_usd", "utilidad_usd", "margen_usd", "beneficio_usd")
        fecha_col = _pick(cols, "fecha", "fecha_venta", "created_at")
        if not nombre_col or not total_col or not fecha_col:
            return pd.DataFrame()
        estado_filter = "AND lower(COALESCE(estado,'')) NOT IN ('anulada','anulado','cancelada','cancelado')" if "estado" in cols else ""
        if ganancia_col:
            ganancia_expr = f"SUM(COALESCE({ganancia_col},0))"
        elif costo_col:
            ganancia_expr = f"SUM(COALESCE({total_col},0) - COALESCE({costo_col},0))"
        else:
            return pd.DataFrame()
        return _read_sql(
            conn,
            f"""
            SELECT COALESCE({nombre_col}, 'Sin nombre') AS item,
                   COUNT(*) AS ventas,
                   COALESCE(SUM({total_col}),0) AS ingreso_usd,
                   COALESCE({ganancia_expr},0) AS ganancia_usd
            FROM ventas
            WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}
            GROUP BY COALESCE({nombre_col}, 'Sin nombre')
            ORDER BY ganancia_usd DESC
            LIMIT 10
            """,
        )


def _build_alerts(metrics: dict[str, float | int]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    if int(metrics.get("stock_critico", 0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Inventario", "alerta": f"Hay {int(metrics['stock_critico'])} producto(s) en o bajo mínimo.", "acción": "Revisar compras y reposición."})
    if int(metrics.get("cierres_diferencia_hoy", 0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Caja", "alerta": f"Hay {int(metrics['cierres_diferencia_hoy'])} cierre(s) con diferencia hoy.", "acción": "Cuadrar efectivo, transferencias, punto y divisas antes de cerrar."})
    if float(metrics.get("utilidad_estimada_mes", 0.0)) < 0:
        alerts.append({"nivel": "Crítica", "área": "Finanzas", "alerta": "La utilidad estimada del mes está negativa.", "acción": "Revisar ventas, gastos, costos y precios."})
    if float(metrics.get("margen_neto_pct", 0.0)) < 15 and float(metrics.get("ventas_mes", 0.0)) > 0:
        alerts.append({"nivel": "Media", "área": "Rentabilidad", "alerta": f"Margen neto bajo: {float(metrics.get('margen_neto_pct', 0.0)):.1f}%.", "acción": "Revisar precios, descuentos, mermas y gastos fijos."})
    if int(metrics.get("reservas_almacen", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Almacén", "alerta": f"Hay {int(metrics['reservas_almacen'])} reserva(s) de material activas.", "acción": "Confirmar liberación o consumo."})
    if int(metrics.get("garantias_vencidas", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Activos", "alerta": f"Hay {int(metrics['garantias_vencidas'])} garantía(s) vencida(s).", "acción": "Actualizar garantía o programar revisión."})
    if int(metrics.get("documentos_activos_pendientes", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Activos", "alerta": f"Hay {int(metrics['documentos_activos_pendientes'])} documento(s) de activos pendientes.", "acción": "Subir factura, garantía o evidencia."})
    if int(metrics.get("bajas_pendientes", 0)) > 0:
        alerts.append({"nivel": "Baja", "área": "Activos", "alerta": f"Hay {int(metrics['bajas_pendientes'])} baja(s) pendientes.", "acción": "Revisar autorización de baja."})
    if int(metrics.get("mantenimiento_abierto", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Mantenimiento", "alerta": f"Hay {int(metrics['mantenimiento_abierto'])} orden(es) de mantenimiento abiertas.", "acción": "Programar o cerrar mantenimiento."})
    return alerts


def _show_df_or_info(df: pd.DataFrame, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_panel_ejecutivo(usuario: str = "Sistema") -> None:
    st.title("📊 Panel ejecutivo")
    st.caption(f"Centro de control financiero, operativo y comercial · {date.today().isoformat()} · Usuario: {usuario}")

    db_metrics = _collect_db_metrics()
    csv_metrics = _collect_csv_metrics()
    metrics = {**db_metrics, **csv_metrics}

    st.subheader("🌅 Pulso de hoy")
    h1, h2, h3, h4, h5 = st.columns(5)
    h1.metric("Ventas hoy", f"${float(metrics.get('ventas_hoy', 0)):,.2f}")
    h2.metric("Gastos hoy", f"${float(metrics.get('gastos_hoy', 0)):,.2f}")
    h3.metric("Utilidad hoy", f"${float(metrics.get('utilidad_estimada_hoy', 0)):,.2f}")
    h4.metric("Tickets hoy", int(metrics.get("tickets_hoy", 0)))
    h5.metric("Ticket promedio", f"${float(metrics.get('venta_promedio_hoy', 0)):,.2f}")

    st.subheader("💼 Salud financiera del mes")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas del mes", f"${float(metrics.get('ventas_mes', 0)):,.2f}")
    c2.metric("Costo ventas", f"${float(metrics.get('costo_ventas_mes', 0)):,.2f}")
    c3.metric("Ganancia bruta", f"${float(metrics.get('ganancia_bruta_mes', 0)):,.2f}", f"{float(metrics.get('margen_bruto_pct', 0)):.1f}%")
    c4.metric("Utilidad neta estimada", f"${float(metrics.get('utilidad_estimada_mes', 0)):,.2f}", f"{float(metrics.get('margen_neto_pct', 0)):.1f}%")

    e1, e2, e3, e4 = st.columns(4)
    e1.metric("Punto equilibrio/día", f"${float(metrics.get('punto_equilibrio_diario', 0)):,.2f}")
    e2.metric("Avance hoy", f"{float(metrics.get('avance_equilibrio_hoy_pct', 0)):,.1f}%")
    e3.metric("Ventas últimos 7 días", f"${float(metrics.get('ventas_7d', 0)):,.2f}")
    e4.metric("Ventas pendientes", int(metrics.get("ventas_pendientes", 0)))

    st.subheader("📦 Operación e inventario")
    o1, o2, o3, o4, o5 = st.columns(5)
    o1.metric("Valor inventario", f"${float(metrics.get('valor_inventario', 0)):,.2f}")
    o2.metric("Stock crítico", int(metrics.get("stock_critico", 0)))
    o3.metric("Reservas almacén", int(metrics.get("reservas_almacen", 0)))
    o4.metric("Merma estimada", f"${float(metrics.get('merma_almacen_usd', 0)):,.2f}")
    o5.metric("Diferencia caja hoy", f"${float(metrics.get('diferencia_caja_hoy', 0)):,.2f}")

    a1, a2, a3, a4 = st.columns(4)
    a1.metric("Activos", int(metrics.get("activos", 0)))
    a2.metric("Valor activos", f"${float(metrics.get('valor_activos', 0)):,.2f}")
    a3.metric("Rutas activas", int(metrics.get("rutas_activas", 0)))
    a4.metric("Mantenimiento abierto", int(metrics.get("mantenimiento_abierto", 0)))

    st.divider()

    alerts = _build_alerts(metrics)
    st.subheader("🚨 Centro de alertas gerenciales")
    if alerts:
        st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
    else:
        st.success("No hay alertas gerenciales críticas detectadas con la información disponible.")

    tab_lineas, tab_inventario, tab_produccion, tab_rentabilidad, tab_acciones = st.tabs([
        "📈 Ventas por línea",
        "📦 Inventario por familia",
        "🏭 Semáforo producción",
        "💰 Top rentabilidad",
        "📌 Acciones",
    ])

    with tab_lineas:
        st.caption("Muestra qué líneas del negocio venden más este mes si la tabla ventas tiene campo de categoría, tipo, área o línea de negocio.")
        _show_df_or_info(_ventas_por_linea_df(), "No hay datos suficientes para separar ventas por línea de negocio.")

    with tab_inventario:
        st.caption("Resume stock, valor y productos críticos por familia/categoría de inventario.")
        _show_df_or_info(_inventario_familia_df(), "No hay datos suficientes para agrupar inventario por familia.")

    with tab_produccion:
        st.caption("Semáforo rápido de pedidos/trabajos según la tabla de producción disponible.")
        _show_df_or_info(_produccion_estado_df(), "No hay órdenes o estados de producción suficientes para mostrar semáforo.")

    with tab_rentabilidad:
        st.caption("Lista productos o servicios más rentables si ventas guarda costo o ganancia por operación.")
        _show_df_or_info(_top_rentabilidad_df(), "No hay datos suficientes de costo/ganancia por venta para calcular rentabilidad por item.")

    with tab_acciones:
        acciones = [
            "Cuadrar caja del día antes de aceptar cierre definitivo.",
            "Revisar productos bajo mínimo antes de aceptar pedidos grandes.",
            "Comparar ventas de hoy contra el punto de equilibrio diario.",
            "Subir precios o revisar costos si el margen neto baja de 15%.",
            "Clasificar cada venta por línea: impresiones, papelería, sublimación, diseño o manualidades.",
            "Registrar costo directo por venta para que el panel calcule rentabilidad real.",
            "Cerrar o actualizar órdenes de producción, despacho y mantenimiento abiertas.",
        ]
        for accion in acciones:
            st.write(f"- {accion}")

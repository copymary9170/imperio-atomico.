from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction

BASE_DIR = Path(__file__).resolve().parents[1]


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone()
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
        return float((row[0] if row else default) or default)
    except Exception:
        return default


def _count(conn: Any, sql: str) -> int:
    return int(_scalar(conn, sql, 0.0))


def _read_sql(conn: Any, sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    try:
        return pd.read_sql_query(sql, conn, params=params)
    except Exception:
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
            fecha_col = _pick(ventas_cols, "fecha", "fecha_venta", "created_at") or "fecha"
            estado_filter = "AND lower(COALESCE(estado,'')) NOT IN ('anulada','anulado','cancelada','cancelado')" if "estado" in ventas_cols else ""
            metrics["ventas_mes"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE strftime('%Y-%m', {fecha_col})=strftime('%Y-%m','now') {estado_filter}")
            metrics["ventas_hoy"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE date({fecha_col})=date('now') {estado_filter}")
            metrics["ventas_7d"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE date({fecha_col})>=date('now','-6 day') {estado_filter}")
            metrics["tickets_hoy"] = _count(conn, f"SELECT COUNT(*) FROM ventas WHERE date({fecha_col})=date('now') {estado_filter}")
            metrics["ventas_pendientes"] = _count(conn, "SELECT COUNT(*) FROM ventas WHERE lower(COALESCE(estado,'')) IN ('pendiente','por cobrar','credito','crédito')" if "estado" in ventas_cols else "SELECT 0")
        else:
            metrics.update({"ventas_mes": 0.0, "ventas_hoy": 0.0, "ventas_7d": 0.0, "tickets_hoy": 0, "ventas_pendientes": 0})

        if _table_exists(conn, "ventas_detalle"):
            det_cols = _columns(conn, "ventas_detalle")
            if {"cantidad", "costo_unitario_usd"}.issubset(det_cols):
                metrics["costo_ventas_mes"] = _scalar(conn, """
                    SELECT COALESCE(SUM(d.cantidad * d.costo_unitario_usd),0)
                    FROM ventas_detalle d JOIN ventas v ON v.id=d.venta_id
                    WHERE strftime('%Y-%m', v.fecha)=strftime('%Y-%m','now')
                      AND lower(COALESCE(v.estado,'')) NOT IN ('anulada','anulado','cancelada','cancelado')
                """)
                metrics["lineas_bajo_costo"] = _count(conn, """
                    SELECT COUNT(*) FROM ventas_detalle
                    WHERE COALESCE(precio_unitario_usd,0) < COALESCE(costo_unitario_usd,0)
                      AND COALESCE(costo_unitario_usd,0) > 0
                """) if {"precio_unitario_usd", "costo_unitario_usd"}.issubset(det_cols) else 0
            else:
                metrics["costo_ventas_mes"] = 0.0
                metrics["lineas_bajo_costo"] = 0
        else:
            metrics["costo_ventas_mes"] = 0.0
            metrics["lineas_bajo_costo"] = 0

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

        inv_cols = _columns(conn, "inventario")
        if inv_cols:
            stock_col = _pick(inv_cols, "stock_actual", "cantidad", "stock", "existencia") or "stock_actual"
            minimo_col = _pick(inv_cols, "stock_minimo", "minimo", "stock_alerta")
            costo_col = _pick(inv_cols, "costo_unitario_usd", "costo_usd", "costo", "precio_compra_usd")
            precio_col = _pick(inv_cols, "precio_venta_usd", "precio_usd", "precio", "precio_publico_usd")
            metrics["productos_inventario"] = _count(conn, "SELECT COUNT(*) FROM inventario")
            metrics["stock_critico"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE COALESCE({stock_col},0) <= COALESCE({minimo_col},0)") if minimo_col else 0
            metrics["valor_inventario"] = _scalar(conn, f"SELECT COALESCE(SUM(COALESCE({stock_col},0) * COALESCE({costo_col},0)),0) FROM inventario") if costo_col else 0.0
            metrics["productos_sin_costo"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE COALESCE({costo_col},0)<=0") if costo_col else 0
            metrics["productos_sin_precio"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE COALESCE({precio_col},0)<=0") if precio_col else 0
            metrics["productos_precio_bajo_costo"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE COALESCE({precio_col},0) <= COALESCE({costo_col},0) AND COALESCE({costo_col},0)>0") if costo_col and precio_col else 0
        else:
            metrics.update({"productos_inventario": 0, "stock_critico": 0, "valor_inventario": 0.0, "productos_sin_costo": 0, "productos_sin_precio": 0, "productos_precio_bajo_costo": 0})

        if _table_exists(conn, "cuentas_por_cobrar"):
            metrics["cxc_total"] = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd),0) FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) NOT IN ('pagada','cerrada','cancelada')")
            metrics["cxc_vencida"] = _scalar(conn, "SELECT COALESCE(SUM(saldo_usd),0) FROM cuentas_por_cobrar WHERE COALESCE(saldo_usd,0)>0 AND fecha_vencimiento IS NOT NULL AND date(fecha_vencimiento)<date('now')")
        else:
            metrics["cxc_total"] = 0.0
            metrics["cxc_vencida"] = 0.0

        metrics["diferencia_caja_hoy"] = _scalar(conn, "SELECT COALESCE(SUM(diferencia_total_usd),0) FROM cierres_caja_turnos WHERE date(fecha_operativa)=date('now')") if _table_exists(conn, "cierres_caja_turnos") and "diferencia_total_usd" in _columns(conn, "cierres_caja_turnos") else 0.0

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
        cols = _columns(conn, "ventas_detalle")
        if _table_exists(conn, "ventas_detalle") and {"descripcion", "cantidad", "subtotal_usd"}.issubset(cols):
            return _read_sql(conn, "SELECT descripcion AS linea, COUNT(*) AS operaciones, COALESCE(SUM(subtotal_usd),0) AS ventas_usd FROM ventas_detalle GROUP BY descripcion ORDER BY ventas_usd DESC LIMIT 12")
    return pd.DataFrame()


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
        return _read_sql(conn, f"SELECT COALESCE({familia_col}, 'Sin familia') AS familia, COUNT(*) AS productos, COALESCE(SUM({stock_col}),0) AS unidades, COALESCE({critico_expr},0) AS criticos, COALESCE({valor_expr},0) AS valor_usd FROM inventario GROUP BY COALESCE({familia_col}, 'Sin familia') ORDER BY criticos DESC, valor_usd DESC LIMIT 15")


def _produccion_estado_df() -> pd.DataFrame:
    candidates = [("ordenes_produccion", "estado"), ("planificacion_produccion", "estado"), ("despachos_entregas", "estado"), ("cola_impresion", "estado")]
    with db_transaction() as conn:
        for table, estado_col in candidates:
            cols = _columns(conn, table)
            if estado_col in cols:
                return _read_sql(conn, f"SELECT '{table}' AS fuente, COALESCE({estado_col}, 'Sin estado') AS estado, COUNT(*) AS cantidad FROM {table} GROUP BY COALESCE({estado_col}, 'Sin estado') ORDER BY cantidad DESC LIMIT 12")
    return pd.DataFrame()


def _top_rentabilidad_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "ventas_detalle"):
            return pd.DataFrame()
        cols = _columns(conn, "ventas_detalle")
        if not {"descripcion", "cantidad", "precio_unitario_usd", "costo_unitario_usd", "subtotal_usd"}.issubset(cols):
            return pd.DataFrame()
        return _read_sql(conn, "SELECT descripcion AS item, COUNT(*) AS ventas, COALESCE(SUM(subtotal_usd),0) AS ingreso_usd, COALESCE(SUM(cantidad * costo_unitario_usd),0) AS costo_usd, COALESCE(SUM(subtotal_usd - (cantidad * costo_unitario_usd)),0) AS ganancia_usd FROM ventas_detalle GROUP BY descripcion ORDER BY ganancia_usd DESC LIMIT 10")


def _ventas_bajo_costo_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "ventas_detalle"):
            return pd.DataFrame()
        cols = _columns(conn, "ventas_detalle")
        if not {"fecha", "descripcion", "cantidad", "precio_unitario_usd", "costo_unitario_usd"}.issubset(cols):
            return pd.DataFrame()
        return _read_sql(conn, "SELECT fecha, descripcion, cantidad, precio_unitario_usd, costo_unitario_usd, (precio_unitario_usd - costo_unitario_usd) AS diferencia_unitaria_usd FROM ventas_detalle WHERE COALESCE(precio_unitario_usd,0) < COALESCE(costo_unitario_usd,0) AND COALESCE(costo_unitario_usd,0) > 0 ORDER BY fecha DESC LIMIT 100")


def _inventario_riesgos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        if not {"nombre", "costo_unitario_usd", "precio_venta_usd", "stock_minimo", "categoria"}.issubset(cols):
            return pd.DataFrame()
        return _read_sql(conn, """
            SELECT sku, nombre, categoria, stock_actual, stock_minimo, costo_unitario_usd, precio_venta_usd,
                   CASE
                     WHEN COALESCE(costo_unitario_usd,0)<=0 THEN 'Sin costo'
                     WHEN COALESCE(precio_venta_usd,0)<=0 THEN 'Sin precio'
                     WHEN COALESCE(precio_venta_usd,0)<=COALESCE(costo_unitario_usd,0) THEN 'Precio bajo o igual al costo'
                     WHEN COALESCE(stock_minimo,0)<=0 THEN 'Sin mínimo definido'
                     WHEN COALESCE(categoria,'')='' THEN 'Sin categoría'
                     ELSE 'OK'
                   END AS riesgo
            FROM inventario
            WHERE COALESCE(costo_unitario_usd,0)<=0 OR COALESCE(precio_venta_usd,0)<=0 OR COALESCE(precio_venta_usd,0)<=COALESCE(costo_unitario_usd,0) OR COALESCE(stock_minimo,0)<=0 OR COALESCE(categoria,'')=''
            ORDER BY riesgo, nombre LIMIT 200
        """)


def _compras_sugeridas_df() -> pd.DataFrame:
    with db_transaction() as conn:
        cols = _columns(conn, "inventario")
        if not {"sku", "nombre", "categoria", "stock_actual", "stock_minimo", "costo_unitario_usd"}.issubset(cols):
            return pd.DataFrame()
        return _read_sql(conn, "SELECT sku, nombre, categoria, stock_actual, stock_minimo, MAX(stock_minimo - stock_actual, 0) AS cantidad_sugerida, costo_unitario_usd, MAX(stock_minimo - stock_actual, 0) * costo_unitario_usd AS inversion_estimada_usd FROM inventario WHERE COALESCE(stock_actual,0) <= COALESCE(stock_minimo,0) ORDER BY inversion_estimada_usd DESC, nombre LIMIT 100")


def _cxc_vencida_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _columns(conn, "cuentas_por_cobrar"):
            return pd.DataFrame()
        return _read_sql(conn, "SELECT cxc.id, cl.nombre AS cliente, cxc.estado, cxc.monto_original_usd, cxc.monto_cobrado_usd, cxc.saldo_usd, cxc.fecha_vencimiento, CAST(julianday(date('now')) - julianday(date(cxc.fecha_vencimiento)) AS INTEGER) AS dias_vencida FROM cuentas_por_cobrar cxc LEFT JOIN clientes cl ON cl.id=cxc.cliente_id WHERE COALESCE(cxc.saldo_usd,0)>0 AND cxc.fecha_vencimiento IS NOT NULL AND date(cxc.fecha_vencimiento) < date('now') ORDER BY date(cxc.fecha_vencimiento) ASC LIMIT 100")


def _caja_metodos_df() -> pd.DataFrame:
    with db_transaction() as conn:
        if _table_exists(conn, "ventas") and {"metodo_pago", "total_usd", "fecha"}.issubset(_columns(conn, "ventas")):
            return _read_sql(conn, "SELECT metodo_pago, COUNT(*) AS operaciones, COALESCE(SUM(total_usd),0) AS total_usd FROM ventas WHERE date(fecha)=date('now') AND lower(COALESCE(estado,'')) NOT IN ('anulada','anulado','cancelada','cancelado') GROUP BY metodo_pago ORDER BY total_usd DESC")
    return pd.DataFrame()


def _datos_minimos_df() -> pd.DataFrame:
    rows = [("Inventario", "sku", "Código único", "BOND-CARTA-001", "Evita duplicados."), ("Inventario", "nombre", "Nombre", "Papel bond carta 75g", "Identifica producto."), ("Inventario", "categoria", "Familia", "Papel / Tinta / Papelería", "Analiza rentabilidad."), ("Inventario", "stock_actual", "Existencia", "50", "Controla stock."), ("Inventario", "stock_minimo", "Mínimo", "10", "Activa compras."), ("Inventario", "costo_unitario_usd", "Costo real", "0.018", "Evita pérdidas."), ("Inventario", "precio_venta_usd", "Precio venta", "0.05", "Calcula margen."), ("Venta detalle", "descripcion", "Producto/servicio", "Impresión color carta", "Top ventas."), ("Venta detalle", "cantidad", "Cantidad", "4", "Costo/ganancia."), ("Venta detalle", "precio_unitario_usd", "Precio cobrado", "0.50", "Detecta barato."), ("Venta detalle", "costo_unitario_usd", "Costo unitario", "0.22", "Detecta pérdida."), ("Venta", "metodo_pago", "Forma pago", "efectivo / pago móvil", "Cuadra caja."), ("CxC", "saldo_usd", "Saldo pendiente", "3.00", "Controla cobro."), ("CxC", "fecha_vencimiento", "Fecha límite", "2026-06-30", "Detecta vencidas.")]
    return pd.DataFrame(rows, columns=["Módulo", "Campo", "Qué llenar", "Ejemplo", "Para qué sirve"])


def _plantilla_inventario_df() -> pd.DataFrame:
    return pd.DataFrame([{"sku": "BOND-CARTA-001", "nombre": "Papel bond carta 75g", "categoria": "Papel", "unidad": "hoja", "stock_actual": 500, "stock_minimo": 100, "costo_unitario_usd": 0.018, "precio_venta_usd": 0.05}])


def _plantilla_ventas_detalle_df() -> pd.DataFrame:
    return pd.DataFrame([{"fecha": "2026-06-14", "descripcion": "Impresión B/N carta", "cantidad": 1, "precio_unitario_usd": 0.25, "costo_unitario_usd": 0.08, "subtotal_usd": 0.25}])


def _build_alerts(metrics: dict[str, float | int]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    if int(metrics.get("lineas_bajo_costo", 0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Precios", "alerta": f"Hay {int(metrics['lineas_bajo_costo'])} línea(s) vendidas por debajo del costo.", "acción": "Revisar precio, costo y tasa antes de repetir la venta."})
    if int(metrics.get("productos_precio_bajo_costo", 0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Inventario", "alerta": f"Hay {int(metrics['productos_precio_bajo_costo'])} producto(s) con precio igual o menor al costo.", "acción": "Actualizar precio de venta o costo unitario."})
    if float(metrics.get("cxc_vencida", 0.0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Cobranza", "alerta": f"Hay ${float(metrics['cxc_vencida']):,.2f} vencidos por cobrar.", "acción": "Contactar clientes y bloquear nuevos créditos sin abono."})
    if int(metrics.get("stock_critico", 0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Inventario", "alerta": f"Hay {int(metrics['stock_critico'])} producto(s) en o bajo mínimo.", "acción": "Revisar compras y reposición."})
    if float(metrics.get("diferencia_caja_hoy", 0.0)) != 0:
        alerts.append({"nivel": "Crítica", "área": "Caja", "alerta": f"Diferencia de caja hoy: ${float(metrics['diferencia_caja_hoy']):,.2f}.", "acción": "Cuadrar efectivo, transferencias, punto y divisas."})
    if int(metrics.get("productos_sin_costo", 0)) or int(metrics.get("productos_sin_precio", 0)):
        alerts.append({"nivel": "Media", "área": "Datos", "alerta": f"Productos sin costo: {int(metrics.get('productos_sin_costo',0))}; sin precio: {int(metrics.get('productos_sin_precio',0))}.", "acción": "Completar datos para que el panel calcule rentabilidad real."})
    if float(metrics.get("utilidad_estimada_mes", 0.0)) < 0:
        alerts.append({"nivel": "Crítica", "área": "Finanzas", "alerta": "La utilidad estimada del mes está negativa.", "acción": "Revisar ventas, gastos, costos y precios."})
    return alerts


def _recommended_actions_df(metrics: dict[str, float | int]) -> pd.DataFrame:
    rows = [("Alta", "Precios", "Ventas bajo costo y productos con precio menor al costo.", "Corregir precio, costo y tasa antes de repetir ventas.", "Evitar pérdidas invisibles."), ("Alta", "Cobranza", "Cuentas por cobrar vencidas y ventas pendientes.", "Contactar clientes, pedir abono y limitar nuevos créditos.", "Recuperar caja."), ("Alta", "Inventario", "Stock crítico y compras sugeridas.", "Comprar primero lo que bloquea ventas.", "No aceptar pedidos sin material."), ("Media", "Caja", "Métodos de pago del día y diferencia de cierre.", "Cuadrar antes de cerrar.", "Caja limpia."), ("Media", "Datos", "Productos sin costo, precio, mínimo o categoría.", "Completar fichas.", "Reportes confiables."), ("Media", "Rentabilidad", "Margen neto y ganancia por item.", "Subir precios o reducir descuentos.", "Proteger utilidad.")]
    return pd.DataFrame(rows, columns=["Prioridad", "Área", "Revisar", "Acción recomendada", "Decisión esperada"])


def _show_df_or_info(df: pd.DataFrame, empty_message: str) -> None:
    if df.empty:
        st.info(empty_message)
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)


def render_panel_ejecutivo(usuario: str = "Sistema", context_key: str = "principal") -> None:
    st.title("📊 Panel ejecutivo")
    st.caption(f"Centro de control financiero, operativo y comercial · {date.today().isoformat()} · Usuario: {usuario}")

    instance_key = f"panel_ejecutivo_{context_key}_{abs(hash(str(usuario))) % 100000}"
    metrics = {**_collect_db_metrics(), **_collect_csv_metrics()}

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
    e3.metric("CxC total", f"${float(metrics.get('cxc_total', 0)):,.2f}")
    e4.metric("CxC vencida", f"${float(metrics.get('cxc_vencida', 0)):,.2f}")

    st.subheader("📦 Operación, inventario y riesgos")
    o1, o2, o3, o4, o5 = st.columns(5)
    o1.metric("Valor inventario", f"${float(metrics.get('valor_inventario', 0)):,.2f}")
    o2.metric("Stock crítico", int(metrics.get("stock_critico", 0)))
    o3.metric("Ventas bajo costo", int(metrics.get("lineas_bajo_costo", 0)))
    o4.metric("Precio ≤ costo", int(metrics.get("productos_precio_bajo_costo", 0)))
    o5.metric("Diferencia caja hoy", f"${float(metrics.get('diferencia_caja_hoy', 0)):,.2f}")

    st.divider()
    alerts = _build_alerts(metrics)
    st.subheader("🚨 Centro de alertas gerenciales")
    if alerts:
        st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
    else:
        st.success("No hay alertas gerenciales críticas detectadas con la información disponible.")

    tabs = st.tabs(["📈 Ventas", "💸 Bajo costo", "📦 Inventario", "🛒 Compras", "💳 CxC", "🏦 Caja", "🏭 Producción", "🧾 Datos mínimos", "📌 Acciones"])
    with tabs[0]:
        _show_df_or_info(_ventas_por_linea_df(), "No hay ventas detalladas suficientes para agrupar.")
        st.markdown("#### Top rentabilidad")
        _show_df_or_info(_top_rentabilidad_df(), "No hay datos suficientes de costo/ganancia por venta.")
    with tabs[1]:
        _show_df_or_info(_ventas_bajo_costo_df(), "No hay ventas registradas por debajo del costo.")
    with tabs[2]:
        st.markdown("#### Inventario por familia")
        _show_df_or_info(_inventario_familia_df(), "No hay datos suficientes para agrupar inventario.")
        st.markdown("#### Riesgos de datos y precios")
        _show_df_or_info(_inventario_riesgos_df(), "No hay productos con datos incompletos o precio bajo costo.")
    with tabs[3]:
        _show_df_or_info(_compras_sugeridas_df(), "No hay compras sugeridas por stock mínimo.")
    with tabs[4]:
        _show_df_or_info(_cxc_vencida_df(), "No hay cuentas por cobrar vencidas.")
    with tabs[5]:
        _show_df_or_info(_caja_metodos_df(), "No hay ventas de hoy separadas por método de pago.")
    with tabs[6]:
        _show_df_or_info(_produccion_estado_df(), "No hay órdenes o estados de producción suficientes.")
    with tabs[7]:
        st.markdown("#### Checklist de datos mínimos")
        st.caption("Completa estos campos para que el ERP calcule caja, margen, compras sugeridas y cuentas por cobrar sin adivinar.")
        st.dataframe(_datos_minimos_df(), use_container_width=True, hide_index=True)
        col_a, col_b = st.columns(2)
        with col_a:
            st.download_button("⬇️ Plantilla inventario CSV", data=_csv_bytes(_plantilla_inventario_df()), file_name="plantilla_inventario_copy_mary.csv", mime="text/csv", use_container_width=True, key=f"{instance_key}_plantilla_inventario_csv")
        with col_b:
            st.download_button("⬇️ Plantilla ventas detalle CSV", data=_csv_bytes(_plantilla_ventas_detalle_df()), file_name="plantilla_ventas_detalle_copy_mary.csv", mime="text/csv", use_container_width=True, key=f"{instance_key}_plantilla_ventas_detalle_csv")
    with tabs[8]:
        st.dataframe(_recommended_actions_df(metrics), use_container_width=True, hide_index=True)

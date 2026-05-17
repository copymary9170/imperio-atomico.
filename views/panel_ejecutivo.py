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
            total_col = "total_usd" if "total_usd" in ventas_cols else "total"
            metrics["ventas_mes"] = _scalar(
                conn,
                f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE strftime('%Y-%m', fecha)=strftime('%Y-%m','now') AND COALESCE(estado,'') NOT IN ('anulada','cancelada')",
            )
            metrics["ventas_pendientes"] = _count(
                conn,
                "SELECT COUNT(*) FROM ventas WHERE lower(COALESCE(estado,'')) IN ('pendiente','por cobrar','credito','crédito')",
            )
        else:
            metrics["ventas_mes"] = 0.0
            metrics["ventas_pendientes"] = 0

        gastos_cols = _columns(conn, "gastos")
        if gastos_cols:
            total_col = "total_usd" if "total_usd" in gastos_cols else "monto_usd" if "monto_usd" in gastos_cols else "total"
            metrics["gastos_mes"] = _scalar(
                conn,
                f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE strftime('%Y-%m', fecha)=strftime('%Y-%m','now') AND COALESCE(estado,'') NOT IN ('anulado','cancelado')",
            )
        else:
            metrics["gastos_mes"] = 0.0

        inventario_cols = _columns(conn, "inventario")
        if inventario_cols:
            stock_col = "stock_actual" if "stock_actual" in inventario_cols else "cantidad" if "cantidad" in inventario_cols else "stock"
            minimo_col = "stock_minimo" if "stock_minimo" in inventario_cols else None
            costo_col = "costo_unitario_usd" if "costo_unitario_usd" in inventario_cols else "costo" if "costo" in inventario_cols else None
            metrics["productos_inventario"] = _count(conn, "SELECT COUNT(*) FROM inventario")
            if minimo_col:
                metrics["stock_critico"] = _count(conn, f"SELECT COUNT(*) FROM inventario WHERE COALESCE({stock_col},0) <= COALESCE({minimo_col},0)")
            else:
                metrics["stock_critico"] = 0
            if costo_col:
                metrics["valor_inventario"] = _scalar(conn, f"SELECT COALESCE(SUM(COALESCE({stock_col},0) * COALESCE({costo_col},0)),0) FROM inventario")
            else:
                metrics["valor_inventario"] = 0.0
        else:
            metrics["productos_inventario"] = 0
            metrics["stock_critico"] = 0
            metrics["valor_inventario"] = 0.0

        activos_cols = _columns(conn, "activos")
        if activos_cols:
            metrics["activos"] = _count(conn, "SELECT COUNT(*) FROM activos WHERE COALESCE(activo,1)=1") if "activo" in activos_cols else _count(conn, "SELECT COUNT(*) FROM activos")
            if "inversion" in activos_cols:
                metrics["valor_activos"] = _scalar(conn, "SELECT COALESCE(SUM(inversion),0) FROM activos WHERE COALESCE(activo,1)=1")
            else:
                metrics["valor_activos"] = 0.0
        else:
            metrics["activos"] = 0
            metrics["valor_activos"] = 0.0

        rutas_cols = _columns(conn, "rutas_produccion")
        if rutas_cols:
            metrics["rutas_activas"] = _count(conn, "SELECT COUNT(*) FROM rutas_produccion WHERE lower(COALESCE(estado,''))='activa'")
        else:
            metrics["rutas_activas"] = 0

        if _table_exists(conn, "industrial_maintenance_orders"):
            metrics["mantenimiento_abierto"] = _count(conn, "SELECT COUNT(*) FROM industrial_maintenance_orders WHERE estado IN ('pendiente','programado','en_ejecucion')")
        else:
            metrics["mantenimiento_abierto"] = 0

    metrics["utilidad_estimada_mes"] = float(metrics.get("ventas_mes", 0.0)) - float(metrics.get("gastos_mes", 0.0))
    return metrics


def _collect_csv_metrics() -> dict[str, float | int]:
    return {
        "reservas_almacen": _estado_count_csv("almacen/material_reservado_pedidos.csv", "estado_pedido", {"pendiente", "en produccion", "en producción", "reservado"}),
        "merma_almacen_usd": _sum_csv("almacen/mermas_almacen.csv", "costo_estimado"),
        "garantias_vencidas": _estado_count_csv("activos/garantias_activos.csv", "estado", {"vencida", "vencido", "expirada", "expirado"}),
        "documentos_activos_pendientes": _estado_count_csv("activos/documentos_activos.csv", "estado", {"pendiente", "faltante", "por subir"}),
        "bajas_pendientes": _estado_count_csv("activos/bajas_activos.csv", "estado", {"borrador", "pendiente", "por aprobar"}),
    }


def _build_alerts(metrics: dict[str, float | int]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []

    if int(metrics.get("stock_critico", 0)) > 0:
        alerts.append({"nivel": "Crítica", "área": "Inventario", "alerta": f"Hay {int(metrics['stock_critico'])} producto(s) en o bajo mínimo.", "acción": "Revisar compras y reposición."})
    if int(metrics.get("reservas_almacen", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Almacén", "alerta": f"Hay {int(metrics['reservas_almacen'])} reserva(s) de material activas.", "acción": "Confirmar liberación o consumo."})
    if float(metrics.get("utilidad_estimada_mes", 0.0)) < 0:
        alerts.append({"nivel": "Crítica", "área": "Finanzas", "alerta": "La utilidad estimada del mes está negativa.", "acción": "Revisar ventas, gastos y precios."})
    if int(metrics.get("garantias_vencidas", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Activos", "alerta": f"Hay {int(metrics['garantias_vencidas'])} garantía(s) vencida(s).", "acción": "Actualizar garantía o programar revisión."})
    if int(metrics.get("documentos_activos_pendientes", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Activos", "alerta": f"Hay {int(metrics['documentos_activos_pendientes'])} documento(s) de activos pendientes.", "acción": "Subir factura, garantía o evidencia."})
    if int(metrics.get("bajas_pendientes", 0)) > 0:
        alerts.append({"nivel": "Baja", "área": "Activos", "alerta": f"Hay {int(metrics['bajas_pendientes'])} baja(s) pendientes.", "acción": "Revisar autorización de baja."})
    if int(metrics.get("mantenimiento_abierto", 0)) > 0:
        alerts.append({"nivel": "Media", "área": "Mantenimiento", "alerta": f"Hay {int(metrics['mantenimiento_abierto'])} orden(es) de mantenimiento abiertas.", "acción": "Programar o cerrar mantenimiento."})

    return alerts


def render_panel_ejecutivo(usuario: str = "Sistema") -> None:
    st.title("📊 Panel ejecutivo")
    st.caption(f"Centro de control del negocio · {date.today().isoformat()} · Usuario: {usuario}")

    db_metrics = _collect_db_metrics()
    csv_metrics = _collect_csv_metrics()
    metrics = {**db_metrics, **csv_metrics}

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas del mes", f"${float(metrics.get('ventas_mes', 0)):,.2f}")
    c2.metric("Gastos del mes", f"${float(metrics.get('gastos_mes', 0)):,.2f}")
    c3.metric("Utilidad estimada", f"${float(metrics.get('utilidad_estimada_mes', 0)):,.2f}")
    c4.metric("Valor inventario", f"${float(metrics.get('valor_inventario', 0)):,.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Stock crítico", int(metrics.get("stock_critico", 0)))
    c6.metric("Activos", int(metrics.get("activos", 0)))
    c7.metric("Rutas activas", int(metrics.get("rutas_activas", 0)))
    c8.metric("Mantenimiento abierto", int(metrics.get("mantenimiento_abierto", 0)))

    c9, c10, c11, c12 = st.columns(4)
    c9.metric("Ventas pendientes", int(metrics.get("ventas_pendientes", 0)))
    c10.metric("Reservas almacén", int(metrics.get("reservas_almacen", 0)))
    c11.metric("Merma estimada", f"${float(metrics.get('merma_almacen_usd', 0)):,.2f}")
    c12.metric("Valor activos", f"${float(metrics.get('valor_activos', 0)):,.2f}")

    st.divider()

    alerts = _build_alerts(metrics)
    st.subheader("🚨 Centro de alertas")
    if alerts:
        st.dataframe(pd.DataFrame(alerts), use_container_width=True, hide_index=True)
    else:
        st.success("No hay alertas críticas detectadas con la información disponible.")

    st.subheader("📌 Próximas acciones recomendadas")
    acciones = [
        "Revisar productos bajo mínimo antes de aceptar nuevos pedidos.",
        "Cerrar o actualizar órdenes de mantenimiento abiertas.",
        "Completar documentos patrimoniales pendientes.",
        "Validar que las reservas de almacén correspondan a pedidos activos.",
        "Revisar utilidad estimada si los gastos del mes superan ventas.",
    ]
    for accion in acciones:
        st.write(f"- {accion}")

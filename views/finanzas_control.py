from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


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
        return float((row[0] if row else default) or default)
    except Exception:
        return float(default)


def _count(conn: Any, sql: str) -> int:
    return int(_scalar(conn, sql, 0.0))


def _load_metrics() -> dict[str, float | int]:
    data: dict[str, float | int] = {}
    with db_transaction() as conn:
        ventas_cols = _columns(conn, "ventas")
        if ventas_cols:
            total_col = "total_usd" if "total_usd" in ventas_cols else "total" if "total" in ventas_cols else None
            fecha_col = "fecha" if "fecha" in ventas_cols else None
            estado_expr = "COALESCE(estado,'') NOT IN ('anulada','cancelada')" if "estado" in ventas_cols else "1=1"
            if total_col and fecha_col:
                data["ventas_mes"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE strftime('%Y-%m',{fecha_col})=strftime('%Y-%m','now') AND {estado_expr}")
                data["ventas_30d"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE date({fecha_col})>=date('now','-30 day') AND {estado_expr}")
                data["ventas_90d"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM ventas WHERE date({fecha_col})>=date('now','-90 day') AND {estado_expr}")
                data["operaciones_ventas"] = _count(conn, f"SELECT COUNT(*) FROM ventas WHERE date({fecha_col})>=date('now','-30 day') AND {estado_expr}")
            else:
                data["ventas_mes"] = data["ventas_30d"] = data["ventas_90d"] = 0.0
                data["operaciones_ventas"] = 0
        else:
            data["ventas_mes"] = data["ventas_30d"] = data["ventas_90d"] = 0.0
            data["operaciones_ventas"] = 0

        gastos_cols = _columns(conn, "gastos")
        if gastos_cols:
            total_col = "total_usd" if "total_usd" in gastos_cols else "monto_usd" if "monto_usd" in gastos_cols else "total" if "total" in gastos_cols else None
            fecha_col = "fecha" if "fecha" in gastos_cols else None
            estado_expr = "COALESCE(estado,'') NOT IN ('anulado','cancelado')" if "estado" in gastos_cols else "1=1"
            if total_col and fecha_col:
                data["gastos_mes"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE strftime('%Y-%m',{fecha_col})=strftime('%Y-%m','now') AND {estado_expr}")
                data["gastos_30d"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE date({fecha_col})>=date('now','-30 day') AND {estado_expr}")
                data["gastos_90d"] = _scalar(conn, f"SELECT COALESCE(SUM({total_col}),0) FROM gastos WHERE date({fecha_col})>=date('now','-90 day') AND {estado_expr}")
            else:
                data["gastos_mes"] = data["gastos_30d"] = data["gastos_90d"] = 0.0
        else:
            data["gastos_mes"] = data["gastos_30d"] = data["gastos_90d"] = 0.0

        caja_cols = _columns(conn, "movimientos_caja")
        if caja_cols:
            monto_col = "monto_usd" if "monto_usd" in caja_cols else "monto" if "monto" in caja_cols else None
            tipo_col = "tipo" if "tipo" in caja_cols else None
            if monto_col and tipo_col:
                data["caja_saldo_estimado"] = _scalar(conn, f"SELECT COALESCE(SUM(CASE WHEN lower({tipo_col}) IN ('ingreso','entrada') THEN {monto_col} ELSE -{monto_col} END),0) FROM movimientos_caja")
            else:
                data["caja_saldo_estimado"] = 0.0
        else:
            data["caja_saldo_estimado"] = 0.0

        if _table_exists(conn, "cuentas_por_cobrar"):
            cols = _columns(conn, "cuentas_por_cobrar")
            saldo_col = "saldo_usd" if "saldo_usd" in cols else "monto_usd" if "monto_usd" in cols else None
            if saldo_col:
                data["cxc_total"] = _scalar(conn, f"SELECT COALESCE(SUM({saldo_col}),0) FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) IN ('pendiente','parcial','vencida','incobrable')")
                data["cxc_vencida"] = _scalar(conn, f"SELECT COALESCE(SUM({saldo_col}),0) FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) IN ('vencida','incobrable')")
                data["cxc_vencidas_count"] = _count(conn, "SELECT COUNT(*) FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) IN ('vencida','incobrable')")
            else:
                data["cxc_total"] = data["cxc_vencida"] = 0.0
                data["cxc_vencidas_count"] = 0
        else:
            data["cxc_total"] = data["cxc_vencida"] = 0.0
            data["cxc_vencidas_count"] = 0

        if _table_exists(conn, "cuentas_por_pagar"):
            cols = _columns(conn, "cuentas_por_pagar")
            saldo_col = "saldo_usd" if "saldo_usd" in cols else "monto_usd" if "monto_usd" in cols else None
            if saldo_col:
                data["cxp_total"] = _scalar(conn, f"SELECT COALESCE(SUM({saldo_col}),0) FROM cuentas_por_pagar WHERE lower(COALESCE(estado,'')) IN ('pendiente','parcial','vencida')")
                data["cxp_vencida"] = _scalar(conn, f"SELECT COALESCE(SUM({saldo_col}),0) FROM cuentas_por_pagar WHERE lower(COALESCE(estado,''))='vencida'")
                data["cxp_vencidas_count"] = _count(conn, "SELECT COUNT(*) FROM cuentas_por_pagar WHERE lower(COALESCE(estado,''))='vencida'")
            else:
                data["cxp_total"] = data["cxp_vencida"] = 0.0
                data["cxp_vencidas_count"] = 0
        else:
            data["cxp_total"] = data["cxp_vencida"] = 0.0
            data["cxp_vencidas_count"] = 0

    data["utilidad_mes"] = float(data.get("ventas_mes", 0)) - float(data.get("gastos_mes", 0))
    data["utilidad_30d"] = float(data.get("ventas_30d", 0)) - float(data.get("gastos_30d", 0))
    data["margen_mes_pct"] = (float(data["utilidad_mes"]) / float(data["ventas_mes"]) * 100) if float(data.get("ventas_mes", 0)) > 0 else 0.0
    data["liquidez_simple"] = (float(data.get("caja_saldo_estimado", 0)) + float(data.get("cxc_total", 0))) / max(float(data.get("cxp_total", 0)), 1.0)
    return data


def _load_breakdowns() -> tuple[pd.DataFrame, pd.DataFrame]:
    with db_transaction() as conn:
        gastos = pd.DataFrame()
        ventas = pd.DataFrame()
        gastos_cols = _columns(conn, "gastos")
        if gastos_cols:
            total_col = "total_usd" if "total_usd" in gastos_cols else "monto_usd" if "monto_usd" in gastos_cols else "total" if "total" in gastos_cols else None
            cat_col = "categoria" if "categoria" in gastos_cols else "concepto" if "concepto" in gastos_cols else None
            fecha_col = "fecha" if "fecha" in gastos_cols else None
            if total_col and cat_col and fecha_col:
                gastos = pd.read_sql_query(
                    f"SELECT COALESCE({cat_col},'Sin categoría') AS categoria, COALESCE(SUM({total_col}),0) AS monto_usd FROM gastos WHERE date({fecha_col})>=date('now','-90 day') GROUP BY COALESCE({cat_col},'Sin categoría') ORDER BY monto_usd DESC",
                    conn,
                )
        ventas_cols = _columns(conn, "ventas")
        if ventas_cols:
            total_col = "total_usd" if "total_usd" in ventas_cols else "total" if "total" in ventas_cols else None
            fecha_col = "fecha" if "fecha" in ventas_cols else None
            cliente_col = "cliente" if "cliente" in ventas_cols else "cliente_nombre" if "cliente_nombre" in ventas_cols else None
            if total_col and fecha_col and cliente_col:
                ventas = pd.read_sql_query(
                    f"SELECT COALESCE({cliente_col},'Sin cliente') AS cliente, COALESCE(SUM({total_col}),0) AS monto_usd FROM ventas WHERE date({fecha_col})>=date('now','-90 day') GROUP BY COALESCE({cliente_col},'Sin cliente') ORDER BY monto_usd DESC LIMIT 20",
                    conn,
                )
        return gastos, ventas


def _score(metrics: dict[str, float | int]) -> tuple[int, str]:
    score = 100
    if float(metrics.get("utilidad_mes", 0)) < 0:
        score -= 35
    if float(metrics.get("margen_mes_pct", 0)) < 10 and float(metrics.get("ventas_mes", 0)) > 0:
        score -= 15
    if float(metrics.get("liquidez_simple", 0)) < 1:
        score -= 25
    if float(metrics.get("cxc_vencida", 0)) > 0:
        score -= 10
    if float(metrics.get("cxp_vencida", 0)) > 0:
        score -= 10
    score = max(0, min(100, score))
    if score >= 80:
        return score, "Saludable"
    if score >= 60:
        return score, "Atención"
    return score, "Crítico"


def render_finanzas_control(usuario: str = "Sistema") -> None:
    st.subheader("📊 Control financiero ejecutivo")
    st.caption("Ventas, gastos, caja, cuentas por cobrar/pagar, liquidez, margen y alertas de salud financiera.")

    metrics = _load_metrics()
    gastos_cat, ventas_cliente = _load_breakdowns()
    score, estado = _score(metrics)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ventas mes", f"${float(metrics.get('ventas_mes', 0)):,.2f}")
    c2.metric("Gastos mes", f"${float(metrics.get('gastos_mes', 0)):,.2f}")
    c3.metric("Utilidad mes", f"${float(metrics.get('utilidad_mes', 0)):,.2f}")
    c4.metric("Margen", f"{float(metrics.get('margen_mes_pct', 0)):,.1f}%")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Caja estimada", f"${float(metrics.get('caja_saldo_estimado', 0)):,.2f}")
    c6.metric("Cuentas por cobrar", f"${float(metrics.get('cxc_total', 0)):,.2f}")
    c7.metric("Cuentas por pagar", f"${float(metrics.get('cxp_total', 0)):,.2f}")
    c8.metric("Liquidez simple", f"{float(metrics.get('liquidez_simple', 0)):,.2f}x")

    st.progress(score / 100)
    st.caption(f"Salud financiera: **{estado}** · Score {score}/100")

    st.divider()

    tab_alertas, tab_gastos, tab_ventas, tab_caja, tab_reco = st.tabs([
        "Alertas",
        "Gastos",
        "Ventas",
        "Caja y obligaciones",
        "Recomendaciones",
    ])

    with tab_alertas:
        alertas = []
        if float(metrics.get("utilidad_mes", 0)) < 0:
            alertas.append({"nivel": "Crítica", "alerta": "Utilidad del mes negativa", "acción": "Reducir gastos o ajustar precios."})
        if float(metrics.get("cxc_vencida", 0)) > 0:
            alertas.append({"nivel": "Media", "alerta": f"Cuentas por cobrar vencidas: ${float(metrics.get('cxc_vencida', 0)):,.2f}", "acción": "Priorizar cobranza."})
        if float(metrics.get("cxp_vencida", 0)) > 0:
            alertas.append({"nivel": "Alta", "alerta": f"Cuentas por pagar vencidas: ${float(metrics.get('cxp_vencida', 0)):,.2f}", "acción": "Negociar o pagar obligaciones críticas."})
        if float(metrics.get("liquidez_simple", 0)) < 1:
            alertas.append({"nivel": "Alta", "alerta": "Liquidez menor a 1x", "acción": "Mejorar caja antes de asumir nuevos compromisos."})
        if not alertas:
            st.success("Sin alertas financieras críticas con la información disponible.")
        else:
            st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)

    with tab_gastos:
        if gastos_cat.empty:
            st.info("No hay desglose de gastos disponible.")
        else:
            st.dataframe(gastos_cat, use_container_width=True, hide_index=True)
            st.bar_chart(gastos_cat.set_index("categoria")["monto_usd"])

    with tab_ventas:
        if ventas_cliente.empty:
            st.info("No hay desglose de ventas por cliente disponible.")
        else:
            st.dataframe(ventas_cliente, use_container_width=True, hide_index=True)
            st.bar_chart(ventas_cliente.set_index("cliente")["monto_usd"])

    with tab_caja:
        resumen = pd.DataFrame([
            {"concepto": "Caja estimada", "monto_usd": float(metrics.get("caja_saldo_estimado", 0))},
            {"concepto": "Cuentas por cobrar", "monto_usd": float(metrics.get("cxc_total", 0))},
            {"concepto": "Cuentas por cobrar vencidas", "monto_usd": float(metrics.get("cxc_vencida", 0))},
            {"concepto": "Cuentas por pagar", "monto_usd": float(metrics.get("cxp_total", 0))},
            {"concepto": "Cuentas por pagar vencidas", "monto_usd": float(metrics.get("cxp_vencida", 0))},
        ])
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        st.bar_chart(resumen.set_index("concepto")["monto_usd"])

    with tab_reco:
        recomendaciones = []
        if float(metrics.get("utilidad_mes", 0)) < 0:
            recomendaciones.append("Revisar precios, descuentos y gastos fijos: el mes está cerrando con pérdida.")
        if float(metrics.get("cxc_vencida", 0)) > 0:
            recomendaciones.append("Crear campaña de cobranza inmediata para clientes vencidos.")
        if float(metrics.get("cxp_vencida", 0)) > 0:
            recomendaciones.append("Ordenar pagos por urgencia para proteger proveedores críticos.")
        if float(metrics.get("liquidez_simple", 0)) < 1:
            recomendaciones.append("Evitar compras no esenciales hasta recuperar liquidez mayor a 1x.")
        recomendaciones.append("Comparar gastos por categoría cada semana para detectar fugas operativas.")
        recomendaciones.append("Conectar ventas, gastos y caja con contabilidad para generar estado de resultados automático.")
        for reco in recomendaciones:
            st.write(f"- {reco}")

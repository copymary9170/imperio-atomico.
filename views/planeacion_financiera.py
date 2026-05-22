from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from modules.planeacion_financiera import (
    render_planeacion_financiera as render_planeacion_financiera_module,
)
from views.caja import render_caja
from views.contabilidad import render_contabilidad
from views.finanzas_control import render_finanzas_control
from views.gastos import render_gastos
from views.presupuesto_mensual import render_presupuesto_mensual
from views.rentabilidad import render_rentabilidad
from views.erp_nuevos_modulos import (
    render_conciliacion_bancaria,
    render_cuentas_por_pagar,
    render_impuestos,
    render_tesoreria,
)


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _columns(conn, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def _scalar(conn, sql: str, default: float = 0.0) -> float:
    try:
        row = conn.execute(sql).fetchone()
        return float((row[0] if row else default) or default)
    except Exception:
        return float(default)


def _render_alertas_financieras(usuario: str) -> None:
    st.subheader("🚨 Alertas financieras")
    st.caption("Caja, flujo, gastos, cuentas por cobrar/pagar, impuestos, conciliaciones y registros contables pendientes.")

    alertas: list[dict] = []
    detalles: dict[str, pd.DataFrame] = {}

    with db_transaction() as conn:
        caja_saldo = 0.0
        if _table_exists(conn, "movimientos_tesoreria"):
            cols = _columns(conn, "movimientos_tesoreria")
            if {"tipo", "monto_usd"}.issubset(cols):
                caja_saldo = _scalar(conn, "SELECT COALESCE(SUM(CASE WHEN lower(tipo) IN ('ingreso','entrada') THEN monto_usd ELSE -monto_usd END),0) FROM movimientos_tesoreria WHERE lower(COALESCE(estado,'')) IN ('confirmado','pagado','')")
        if caja_saldo < 0:
            alertas.append({"nivel": "Alta", "alerta": "Caja estimada negativa", "cantidad": 1, "acción": "Revisar movimientos de tesorería y cerrar caja."})

        if _table_exists(conn, "gastos"):
            cols = _columns(conn, "gastos")
            cat_col = "categoria" if "categoria" in cols else "concepto" if "concepto" in cols else None
            if cat_col:
                sin_categoria = pd.read_sql_query(f"SELECT * FROM gastos WHERE COALESCE({cat_col},'')='' LIMIT 200", conn)
                detalles["Gastos sin categoría"] = sin_categoria
                if not sin_categoria.empty:
                    alertas.append({"nivel": "Media", "alerta": "Gastos sin categoría", "cantidad": len(sin_categoria), "acción": "Clasificar gastos para mejorar reportes y presupuesto."})

        if _table_exists(conn, "cuentas_por_cobrar"):
            vencidas = pd.read_sql_query("SELECT * FROM cuentas_por_cobrar WHERE lower(COALESCE(estado,'')) IN ('vencida','incobrable') LIMIT 200", conn)
            detalles["CxC vencidas"] = vencidas
            if not vencidas.empty:
                alertas.append({"nivel": "Alta", "alerta": "Cuentas por cobrar vencidas", "cantidad": len(vencidas), "acción": "Priorizar cobranza y seguimiento a clientes."})

        if _table_exists(conn, "cuentas_por_pagar"):
            vencidas = pd.read_sql_query("SELECT * FROM cuentas_por_pagar WHERE lower(COALESCE(estado,''))='vencida' LIMIT 200", conn)
            detalles["CxP vencidas"] = vencidas
            if not vencidas.empty:
                alertas.append({"nivel": "Alta", "alerta": "Cuentas por pagar vencidas", "cantidad": len(vencidas), "acción": "Ordenar pagos críticos o renegociar proveedores."})

        if _table_exists(conn, "conciliaciones_bancarias"):
            pendientes = pd.read_sql_query("SELECT * FROM conciliaciones_bancarias WHERE lower(COALESCE(estado,'')) IN ('pendiente','abierta','por conciliar') LIMIT 200", conn)
            detalles["Conciliaciones pendientes"] = pendientes
            if not pendientes.empty:
                alertas.append({"nivel": "Media", "alerta": "Conciliaciones pendientes", "cantidad": len(pendientes), "acción": "Conciliar bancos contra caja/tesorería."})

        if _table_exists(conn, "impuestos"):
            pendientes = pd.read_sql_query("SELECT * FROM impuestos WHERE lower(COALESCE(estado,'')) IN ('pendiente','vencido','por pagar') LIMIT 200", conn)
            detalles["Impuestos pendientes"] = pendientes
            if not pendientes.empty:
                alertas.append({"nivel": "Alta", "alerta": "Impuestos pendientes o vencidos", "cantidad": len(pendientes), "acción": "Revisar calendario fiscal y pagos."})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Caja estimada", f"${caja_saldo:,.2f}")
    c2.metric("Alertas", len(alertas))
    c3.metric("CxC vencidas", len(detalles.get("CxC vencidas", pd.DataFrame())))
    c4.metric("CxP vencidas", len(detalles.get("CxP vencidas", pd.DataFrame())))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas financieras críticas con la información disponible.")

    if detalles:
        tabs = st.tabs(list(detalles.keys()))
        for tab, (nombre, df) in zip(tabs, detalles.items()):
            with tab:
                if df.empty:
                    st.success("Sin registros.")
                else:
                    st.dataframe(df, use_container_width=True, hide_index=True)


def render_planeacion_financiera(usuario: str) -> None:
    st.title("💼 Finanzas")
    st.caption("Hub financiero: resumen ejecutivo, planeación, presupuesto mensual, caja, tesorería, gastos, cuentas por pagar, contabilidad, conciliación, impuestos, rentabilidad y alertas.")

    secciones = {
        "📊 Resumen ejecutivo": lambda: render_finanzas_control(usuario),
        "💰 Planeación / Presupuesto": lambda: render_planeacion_financiera_module(usuario),
        "📅 Presupuesto mensual": lambda: render_presupuesto_mensual(usuario),
        "🏦 Caja": lambda: render_caja(usuario),
        "🏦 Tesorería y cobranza": lambda: render_tesoreria(usuario),
        "📉 Gastos": lambda: render_gastos(usuario),
        "💸 Cuentas por pagar": lambda: render_cuentas_por_pagar(usuario),
        "📚 Contabilidad": lambda: render_contabilidad(usuario),
        "🏛️ Conciliación bancaria": lambda: render_conciliacion_bancaria(usuario),
        "🧾 Impuestos": lambda: render_impuestos(usuario),
        "📈 Rentabilidad": lambda: render_rentabilidad(usuario),
        "🚨 Alertas financieras": lambda: _render_alertas_financieras(usuario),
    }

    seccion = st.radio(
        "Sección financiera",
        list(secciones.keys()),
        horizontal=True,
        key="finanzas_seccion_activa",
    )
    st.divider()
    secciones[seccion]()

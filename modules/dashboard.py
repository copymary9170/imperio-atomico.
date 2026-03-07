from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from utils.calculations import calculate_daily_profit


def _scalar(conn, query: str, params: tuple = ()) -> float:
    row = conn.execute(query, params).fetchone()
    return float(row[0] or 0.0)


def render_dashboard() -> None:
    st.subheader("Dashboard Financiero")
    with db_transaction() as conn:
        daily_revenue = _scalar(conn, "SELECT SUM(total_usd) FROM ventas WHERE date(fecha)=date('now') AND estado='registrada'")
        daily_expenses = _scalar(conn, "SELECT SUM(monto_usd) FROM gastos WHERE date(fecha)=date('now') AND estado='activo'")
        daily_production_cost = _scalar(
            conn,
            """
            SELECT SUM(costo_unitario_usd * cantidad) FROM ventas_detalle
            WHERE date(fecha)=date('now') AND estado='activo'
            """,
        )
        monthly_profit = _scalar(
            conn,
            """
            SELECT COALESCE(SUM(v.total_usd), 0) - COALESCE((SELECT SUM(g.monto_usd) FROM gastos g WHERE strftime('%Y-%m', g.fecha)=strftime('%Y-%m', 'now') AND g.estado='activo'), 0)
            FROM ventas v WHERE strftime('%Y-%m', v.fecha)=strftime('%Y-%m', 'now') AND v.estado='registrada'
            """,
        )
        monthly_sales = _scalar(
            conn,
            "SELECT SUM(total_usd) FROM ventas WHERE strftime('%Y-%m', fecha)=strftime('%Y-%m', 'now') AND estado='registrada'",
        )
        top_expense = conn.execute(
            "SELECT categoria, SUM(monto_usd) total FROM gastos WHERE estado='activo' GROUP BY categoria ORDER BY total DESC LIMIT 1"
        ).fetchone()
        best_product = conn.execute(
            """
            SELECT descripcion, SUM(cantidad) qty
            FROM ventas_detalle
            WHERE estado='activo'
            GROUP BY descripcion
            ORDER BY qty DESC LIMIT 1
            """
        ).fetchone()

    daily_profit = calculate_daily_profit(daily_revenue, daily_expenses, daily_production_cost)
    margin = (daily_profit / daily_revenue * 100) if daily_revenue else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos diarios", f"$ {daily_revenue:,.2f}")
    c2.metric("Gastos diarios", f"$ {daily_expenses:,.2f}")
    c3.metric("Ganancia diaria", f"$ {daily_profit:,.2f}", delta=f"{margin:,.2f}% margen")
    c4.metric("Ganancia mensual", f"$ {monthly_profit:,.2f}")

    c5, c6 = st.columns(2)
    c5.metric("Ventas del mes", f"$ {monthly_sales:,.2f}")
    c6.metric("Costo productivo diario", f"$ {daily_production_cost:,.2f}")

    st.info(f"Categoría de mayor gasto: {top_expense['categoria'] if top_expense else 'N/A'}")
    st.info(f"Producto más vendido: {best_product['descripcion'] if best_product else 'N/A'}")

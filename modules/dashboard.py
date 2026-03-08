from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from utils.calculations import calculate_daily_profit


# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def _scalar(conn, query: str, params: tuple = ()) -> float:
    """
    Ejecuta una consulta SQL que devuelve un único valor numérico.
    """
    row = conn.execute(query, params).fetchone()

    if not row:
        return 0.0

    try:
        return float(row[0] or 0.0)
    except Exception:
        return 0.0


# ============================================================
# DASHBOARD FINANCIERO
# ============================================================

def render_dashboard() -> None:

    st.subheader("📊 Dashboard Financiero")

    try:

        with db_transaction() as conn:

            # -----------------------------
            # INGRESOS DEL DÍA
            # -----------------------------

            daily_revenue = _scalar(
                conn,
                """
                SELECT SUM(total_usd)
                FROM ventas
                WHERE date(fecha)=date('now')
                AND estado='registrada'
                """
            )

            # -----------------------------
            # GASTOS DEL DÍA
            # -----------------------------

            daily_expenses = _scalar(
                conn,
                """
                SELECT SUM(monto_usd)
                FROM gastos
                WHERE date(fecha)=date('now')
                AND estado='activo'
                """
            )

            # -----------------------------
            # COSTO PRODUCTIVO
            # -----------------------------

            daily_production_cost = _scalar(
                conn,
                """
                SELECT SUM(costo_unitario_usd * cantidad)
                FROM ventas_detalle
                WHERE date(fecha)=date('now')
                AND estado='activo'
                """
            )

            # -----------------------------
            # GANANCIA MENSUAL
            # -----------------------------

            monthly_profit = _scalar(
                conn,
                """
                SELECT
                COALESCE(SUM(v.total_usd),0)
                -
                COALESCE(
                    (
                        SELECT SUM(g.monto_usd)
                        FROM gastos g
                        WHERE strftime('%Y-%m', g.fecha)=strftime('%Y-%m','now')
                        AND g.estado='activo'
                    ),
                0)
                FROM ventas v
                WHERE strftime('%Y-%m', v.fecha)=strftime('%Y-%m','now')
                AND v.estado='registrada'
                """
            )

            # -----------------------------
            # VENTAS DEL MES
            # -----------------------------

            monthly_sales = _scalar(
                conn,
                """
                SELECT SUM(total_usd)
                FROM ventas
                WHERE strftime('%Y-%m',fecha)=strftime('%Y-%m','now')
                AND estado='registrada'
                """
            )

            # -----------------------------
            # CATEGORÍA CON MÁS GASTO
            # -----------------------------

            top_expense = conn.execute(
                """
                SELECT categoria, SUM(monto_usd) total
                FROM gastos
                WHERE estado='activo'
                GROUP BY categoria
                ORDER BY total DESC
                LIMIT 1
                """
            ).fetchone()

            # -----------------------------
            # PRODUCTO MÁS VENDIDO
            # -----------------------------

            best_product = conn.execute(
                """
                SELECT descripcion, SUM(cantidad) qty
                FROM ventas_detalle
                WHERE estado='activo'
                GROUP BY descripcion
                ORDER BY qty DESC
                LIMIT 1
                """
            ).fetchone()

    except Exception as e:

        st.error("Error cargando dashboard")

        st.exception(e)

        return

    # ============================================================
    # CÁLCULOS
    # ============================================================

    daily_profit = calculate_daily_profit(
        daily_revenue,
        daily_expenses,
        daily_production_cost
    )

    margin = (daily_profit / daily_revenue * 100) if daily_revenue else 0.0

    # ============================================================
    # MÉTRICAS PRINCIPALES
    # ============================================================

    c1, c2, c3, c4 = st.columns(4)

    c1.metric(
        "Ingresos diarios",
        f"$ {daily_revenue:,.2f}"
    )

    c2.metric(
        "Gastos diarios",
        f"$ {daily_expenses:,.2f}"
    )

    c3.metric(
        "Ganancia diaria",
        f"$ {daily_profit:,.2f}",
        delta=f"{margin:,.2f}% margen"
    )

    c4.metric(
        "Ganancia mensual",
        f"$ {monthly_profit:,.2f}"
    )

    st.divider()

    # ============================================================
    # MÉTRICAS SECUNDARIAS
    # ============================================================

    c5, c6 = st.columns(2)

    c5.metric(
        "Ventas del mes",
        f"$ {monthly_sales:,.2f}"
    )

    c6.metric(
        "Costo productivo diario",
        f"$ {daily_production_cost:,.2f}"
    )

    st.divider()

    # ============================================================
    # INSIGHTS
    # ============================================================

    if top_expense:

        st.info(
            f"💸 Categoría con mayor gasto: **{top_expense['categoria']}**"
        )

    else:

        st.info("No hay gastos registrados.")

    if best_product:

        st.success(
            f"🏆 Producto más vendido: **{best_product['descripcion']}**"
        )

    else:

        st.info("No hay ventas registradas.")

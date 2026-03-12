from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _sum_method(df: pd.DataFrame, method: str, column: str) -> float:
    if df.empty:
        return 0.0
    return float(df[df["metodo_pago"].str.lower() == method.lower()][column].sum())


# ============================================================
# INTERFAZ DE CIERRE DE CAJA
# ============================================================
def render_caja(usuario: str, user_role: str) -> None:
    st.subheader("🏁 Cierre de caja y arqueo diario")

    if user_role not in ["Admin", "Administration", "Administracion"]:
        st.warning("Solo usuarios de administración pueden realizar cierres de caja.")
        return

    fecha_cierre = st.date_input("Seleccionar fecha", value=date.today())
    fecha_str = fecha_cierre.strftime("%Y-%m-%d")

    try:
        with db_transaction() as conn:
            ventas = pd.read_sql_query(
                """
                SELECT id, fecha, metodo_pago, total_usd
                FROM ventas
                WHERE estado='registrada' AND date(fecha)=?
                """,
                conn,
                params=(fecha_str,),
            )

            gastos = pd.read_sql_query(
                """
                SELECT id, fecha, metodo_pago, monto_usd
                FROM gastos
                WHERE date(fecha)=?
                """,
                conn,
                params=(fecha_str,),
            )

            historial = pd.read_sql_query(
                """
                SELECT
                    id,
                    fecha,
                    usuario,
                    cash_start,
                    sales_cash,
                    sales_transfer,
                    sales_zelle,
                    sales_binance,
                    expenses_cash,
                    expenses_transfer,
                    cash_end,
                    observaciones
                FROM cierres_caja
                ORDER BY id DESC
                LIMIT 30
                """,
                conn,
            )
    except Exception as e:
        st.error("Error cargando datos de caja")
        st.exception(e)
        return

    ventas["metodo_pago"] = ventas["metodo_pago"].fillna("sin definir")
    gastos["metodo_pago"] = gastos["metodo_pago"].fillna("sin definir")

    sales_cash = _sum_method(ventas, "efectivo", "total_usd")
    sales_transfer = _sum_method(ventas, "transferencia", "total_usd")
    sales_zelle = _sum_method(ventas, "zelle", "total_usd")
    sales_binance = _sum_method(ventas, "binance", "total_usd")

    expenses_cash = _sum_method(gastos, "efectivo", "monto_usd")
    expenses_transfer = _sum_method(gastos, "transferencia", "monto_usd")

    cash_start = st.number_input("Fondo inicial de caja (USD)", min_value=0.0, value=0.0, step=1.0)
    observaciones = st.text_area("Observaciones del cierre", placeholder="Notas de cierre, incidencias, arqueo...")

    cash_end = cash_start + sales_cash - expenses_cash

    m1, m2, m3 = st.columns(3)
    m1.metric("Ventas del día", f"$ {float(ventas['total_usd'].sum()):,.2f}")
    m2.metric("Gastos del día", f"$ {float(gastos['monto_usd'].sum()):,.2f}")
    m3.metric("Efectivo final estimado", f"$ {cash_end:,.2f}")

    with st.expander("Ver desglose por método"):
        c1, c2 = st.columns(2)
        with c1:
            st.caption("Ingresos")
            st.write(f"Efectivo: $ {sales_cash:,.2f}")
            st.write(f"Transferencia: $ {sales_transfer:,.2f}")
            st.write(f"Zelle: $ {sales_zelle:,.2f}")
            st.write(f"Binance: $ {sales_binance:,.2f}")
        with c2:
            st.caption("Egresos")
            st.write(f"Efectivo: $ {expenses_cash:,.2f}")
            st.write(f"Transferencia: $ {expenses_transfer:,.2f}")

    if st.button("💾 Guardar cierre del día"):
        try:
            with db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO cierres_caja (
                        fecha,
                        usuario,
                        estado,
                        cash_start,
                        sales_cash,
                        sales_transfer,
                        sales_zelle,
                        sales_binance,
                        expenses_cash,
                        expenses_transfer,
                        cash_end,
                        observaciones
                    )
                    VALUES (?, ?, 'cerrado', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fecha_str,
                        usuario,
                        float(cash_start),
                        float(sales_cash),
                        float(sales_transfer),
                        float(sales_zelle),
                        float(sales_binance),
                        float(expenses_cash),
                        float(expenses_transfer),
                        float(cash_end),
                        observaciones.strip() if observaciones else None,
                    ),
                )

            st.success("✅ Cierre registrado correctamente")
            st.rerun()
        except Exception as e:
            st.error("Error guardando cierre")
            st.exception(e)

    st.divider()
    st.subheader("📜 Historial de cierres")

    if historial.empty:
        st.info("Aún no hay cierres guardados.")
        return

    st.dataframe(historial, use_container_width=True, hide_index=True)

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        historial.to_excel(writer, index=False, sheet_name="Cierres")

    st.download_button(
        "📥 Descargar historial de cierres",
        buffer.getvalue(),
        file_name="cierres_caja.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

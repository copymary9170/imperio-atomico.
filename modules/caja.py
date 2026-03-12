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
@@ -226,25 +232,27 @@ def render_caja(usuario: str, user_role: str) -> None:
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

from __future__ import annotations

import io
from datetime import date

import pandas as pd
import streamlit as st

from database.connection import db_transaction


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
                WHERE estado='activo' AND date(fecha)=?
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

    ventas["metodo_pago"] = ventas.get("metodo_pago", "").fillna("") if not ventas.empty else ""

    cobradas = ventas[ventas["metodo_pago"].str.lower() != "credito"] if not ventas.empty else pd.DataFrame()
    pendientes = ventas[ventas["metodo_pago"].str.lower() == "credito"] if not ventas.empty else pd.DataFrame()

    t_ventas_cobradas = float(cobradas["total_usd"].sum()) if not cobradas.empty else 0.0
    t_pendientes = float(pendientes["total_usd"].sum()) if not pendientes.empty else 0.0
    t_gastos = float(gastos["monto_usd"].sum()) if not gastos.empty else 0.0
    balance_dia = t_ventas_cobradas - t_gastos

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos cobrados", f"$ {t_ventas_cobradas:,.2f}")
    c2.metric("Cuentas pendientes", f"$ {t_pendientes:,.2f}")
    c3.metric("Egresos del día", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c4.metric("Neto en caja", f"$ {balance_dia:,.2f}")

    st.divider()

    col_v, col_g = st.columns(2)
    with col_v:
        st.subheader("💰 Ingresos por método")
        if cobradas.empty:
            st.info("No hubo ingresos cobrados.")
        else:
            for metodo, monto in cobradas.groupby("metodo_pago")["total_usd"].sum().items():
                st.write(f"✅ **{metodo}:** $ {float(monto):,.2f}")

    with col_g:
        st.subheader("💸 Egresos por método")
        if gastos.empty:
            st.info("No hubo gastos.")
        else:
            for metodo, monto in gastos.groupby("metodo_pago")["monto_usd"].sum().items():
                st.write(f"❌ **{metodo}:** $ {float(monto):,.2f}")

    with st.expander("📝 Ver detalle completo"):
        st.write("### Ventas cobradas")
        st.dataframe(cobradas, use_container_width=True, hide_index=True)
        st.write("### Ventas pendientes")
        st.dataframe(pendientes, use_container_width=True, hide_index=True)
        st.write("### Gastos")
        st.dataframe(gastos, use_container_width=True, hide_index=True)

    st.divider()

    cash_start = st.number_input("Caja inicial del día ($)", min_value=0.0, value=0.0, step=1.0)
    cash_end = cash_start + balance_dia
    st.metric("Caja final estimada", f"$ {cash_end:,.2f}")
    obs = st.text_area("Observaciones del cierre")

    if st.button("💾 Guardar cierre del día"):
        sales_cash = float(cobradas[cobradas["metodo_pago"].str.lower() == "efectivo"]["total_usd"].sum()) if not cobradas.empty else 0.0
        sales_transfer = float(cobradas[cobradas["metodo_pago"].str.lower() == "transferencia"]["total_usd"].sum()) if not cobradas.empty else 0.0
        sales_zelle = float(cobradas[cobradas["metodo_pago"].str.lower() == "zelle"]["total_usd"].sum()) if not cobradas.empty else 0.0
        sales_binance = float(cobradas[cobradas["metodo_pago"].str.lower() == "binance"]["total_usd"].sum()) if not cobradas.empty else 0.0

        expenses_cash = float(gastos[gastos["metodo_pago"].str.lower() == "efectivo"]["monto_usd"].sum()) if not gastos.empty else 0.0
        expenses_transfer = float(gastos[gastos["metodo_pago"].str.lower().isin(["transferencia", "pago móvil"])]["monto_usd"].sum()) if not gastos.empty else 0.0

        try:
            with db_transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO cierres_caja (
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        fecha_str,
                        usuario,
                        float(cash_start),
                        sales_cash,
                        sales_transfer,
                        sales_zelle,
                        sales_binance,
                        expenses_cash,
                        expenses_transfer,
                        float(cash_end),
                        obs,
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
    )

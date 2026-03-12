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
@@ -44,144 +50,208 @@ def render_caja(usuario: str, user_role: str) -> None:
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

            cierre_existente = conn.execute(
                "SELECT id, cash_end FROM cierres_caja WHERE fecha=? ORDER BY id DESC LIMIT 1",
                (fecha_str,),
            ).fetchone()
    except Exception as e:
        st.error("Error cargando datos de caja")
        st.exception(e)
        return

    if cierre_existente:
        st.info(f"ℹ️ Ya existe un cierre para esta fecha (ID #{int(cierre_existente['id'])}).")

    if ventas.empty:
        ventas = pd.DataFrame(columns=["id", "fecha", "metodo_pago", "total_usd"])
    if gastos.empty:
        gastos = pd.DataFrame(columns=["id", "fecha", "metodo_pago", "monto_usd"])

    ventas["metodo_pago"] = ventas["metodo_pago"].fillna("")
    gastos["metodo_pago"] = gastos["metodo_pago"].fillna("")

    cobradas = ventas[ventas["metodo_pago"].str.lower() != "credito"]
    pendientes = ventas[ventas["metodo_pago"].str.lower() == "credito"]

    t_ventas_cobradas = float(cobradas["total_usd"].sum())
    t_pendientes = float(pendientes["total_usd"].sum())
    t_gastos = float(gastos["monto_usd"].sum())
    balance_dia = t_ventas_cobradas - t_gastos

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos cobrados", f"$ {t_ventas_cobradas:,.2f}")
    c2.metric("Cuentas pendientes", f"$ {t_pendientes:,.2f}")
    c3.metric("Egresos del día", f"$ {t_gastos:,.2f}", delta_color="inverse")
    c4.metric("Neto en caja", f"$ {balance_dia:,.2f}")

    st.divider()

    met_ventas = (
        cobradas.groupby("metodo_pago", as_index=False)["total_usd"]
        .sum()
        .sort_values("total_usd", ascending=False)
    )
    met_gastos = (
        gastos.groupby("metodo_pago", as_index=False)["monto_usd"]
        .sum()
        .sort_values("monto_usd", ascending=False)
    )

    col_v, col_g = st.columns(2)
    with col_v:
        st.subheader("💰 Ingresos por método")
        if met_ventas.empty:
            st.info("No hubo ingresos cobrados.")
        else:
            st.dataframe(met_ventas, use_container_width=True, hide_index=True)
            st.bar_chart(met_ventas.set_index("metodo_pago")["total_usd"])

    with col_g:
        st.subheader("💸 Egresos por método")
        if met_gastos.empty:
            st.info("No hubo gastos.")
        else:
            st.dataframe(met_gastos, use_container_width=True, hide_index=True)
            st.bar_chart(met_gastos.set_index("metodo_pago")["monto_usd"])

    with st.expander("📝 Ver detalle completo"):
        st.write("### Ventas cobradas")
        st.dataframe(cobradas, use_container_width=True, hide_index=True)
        st.write("### Ventas pendientes")
        st.dataframe(pendientes, use_container_width=True, hide_index=True)
        st.write("### Gastos")
        st.dataframe(gastos, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Arqueo inteligente de efectivo")

    cash_start = st.number_input("Caja inicial del día ($)", min_value=0.0, value=0.0, step=1.0)
    ventas_efectivo = _sum_method(cobradas, "efectivo", "total_usd")
    gastos_efectivo = _sum_method(gastos, "efectivo", "monto_usd")
    cash_teorico = cash_start + ventas_efectivo - gastos_efectivo

    a1, a2, a3 = st.columns(3)
    a1.metric("Efectivo teórico", f"$ {cash_teorico:,.2f}")
    a2.metric("Ventas efectivo", f"$ {ventas_efectivo:,.2f}")
    a3.metric("Gastos efectivo", f"$ {gastos_efectivo:,.2f}", delta_color="inverse")

    st.caption("Ingresa conteo rápido por denominaciones (USD).")
    d1, d2, d3, d4, d5 = st.columns(5)
    billetes_100 = d1.number_input("$100", min_value=0, value=0, step=1)
    billetes_50 = d2.number_input("$50", min_value=0, value=0, step=1)
    billetes_20 = d3.number_input("$20", min_value=0, value=0, step=1)
    billetes_10 = d4.number_input("$10", min_value=0, value=0, step=1)
    billetes_5 = d5.number_input("$5", min_value=0, value=0, step=1)

    e1, e2, e3 = st.columns(3)
    billetes_1 = e1.number_input("$1", min_value=0, value=0, step=1)
    monedas = e2.number_input("Monedas ($)", min_value=0.0, value=0.0, step=0.25)
    cash_real = (
        billetes_100 * 100
        + billetes_50 * 50
        + billetes_20 * 20
        + billetes_10 * 10
        + billetes_5 * 5
        + billetes_1
        + monedas
    )
    e3.metric("Efectivo contado", f"$ {cash_real:,.2f}")

    diferencia = cash_real - cash_teorico
    estado_arqueo = "✅ Cuadrado" if abs(diferencia) < 0.01 else ("⚠️ Sobrante" if diferencia > 0 else "⚠️ Faltante")
    st.metric("Diferencia arqueo", f"$ {diferencia:,.2f}", delta=f"$ {diferencia:,.2f}")
    st.write(f"Estado: **{estado_arqueo}**")

    cash_end = cash_start + balance_dia
    st.metric("Caja final global estimada", f"$ {cash_end:,.2f}")
    obs = st.text_area("Observaciones del cierre")

    if st.button("💾 Guardar cierre del día"):
        sales_cash = _sum_method(cobradas, "efectivo", "total_usd")
        sales_transfer = _sum_method(cobradas, "transferencia", "total_usd")
        sales_zelle = _sum_method(cobradas, "zelle", "total_usd")
        sales_binance = _sum_method(cobradas, "binance", "total_usd")

        expenses_cash = _sum_method(gastos, "efectivo", "monto_usd")
        expenses_transfer = float(
            gastos[gastos["metodo_pago"].str.lower().isin(["transferencia", "pago móvil"])]["monto_usd"].sum()
        )

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
                        f"{obs}\nArqueo real: {cash_real:.2f} | Diferencia: {diferencia:.2f}",
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
modules/gastos.py
modules/gastos.py

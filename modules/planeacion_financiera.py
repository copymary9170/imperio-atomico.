from __future__ import annotations

from datetime import date
import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.planeacion_financiera_service import (
    calcular_flujo_caja_proyectado,
    generar_alertas_gerenciales,
    guardar_presupuesto_operativo,
    listar_presupuesto_operativo,
    resumen_presupuesto_operativo,
)

# NUEVO: puedes conectar luego a servicios reales
# (por ahora placeholders seguros)
def _placeholder_df(columns):
    return pd.DataFrame(columns=columns)


def render_planeacion_financiera(usuario: str) -> None:
    st.title("💰 Planeación Financiera")
    st.caption("Módulo operativo: presupuesto, flujo de caja, ingresos, costos y control financiero.")

    periodo_default = date.today().strftime("%Y-%m")
    periodo = st.text_input("Período (YYYY-MM)", value=periodo_default)

    # =========================
    # DATA BASE
    # =========================
    with db_transaction() as conn:
        resumen = resumen_presupuesto_operativo(conn, periodo=periodo)
        flujo = calcular_flujo_caja_proyectado(conn)
        alertas = generar_alertas_gerenciales(conn, periodo=periodo)
        presupuesto = listar_presupuesto_operativo(conn, periodo=periodo)

    # =========================
    # DASHBOARD
    # =========================
    st.subheader("📊 Dashboard financiero")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Saldo actual", f"$ {float(flujo.iloc[0]['saldo_actual_usd']) if not flujo.empty else 0:,.2f}")
    c2.metric("Flujo 30d", f"$ {float(flujo.iloc[-1]['flujo_proyectado_usd']) if not flujo.empty else 0:,.2f}")
    c3.metric("Pagos 30d", f"$ {float(flujo.iloc[-1]['pagos_proximos_usd']) if not flujo.empty else 0:,.2f}")
    c4.metric("Cobros 30d", f"$ {float(flujo.iloc[-1]['cobros_esperados_usd']) if not flujo.empty else 0:,.2f}")
    c5.metric("Desviación egresos", f"$ {float(resumen.get('desviacion_egresos_usd', 0)):,.2f}")

    # =========================
    # NAVEGACIÓN
    # =========================
    tabs = st.tabs([
        "Flujo de Caja",
        "Presupuesto",
        "Ingresos",
        "Costos",
        "KPIs",
        "Alertas"
    ])

    # =========================
    # FLUJO DE CAJA
    # =========================
    with tabs[0]:
        st.subheader("💸 Flujo de caja proyectado")
        st.dataframe(flujo, use_container_width=True, hide_index=True)

        if not flujo.empty:
            st.line_chart(flujo.set_index("fecha")[["flujo_proyectado_usd"]])

        st.download_button(
            "Exportar CSV",
            flujo.to_csv(index=False).encode(),
            f"flujo_{periodo}.csv",
        )

    # =========================
    # PRESUPUESTO
    # =========================
    with tabs[1]:
        st.subheader("📅 Presupuesto operativo")

        st.dataframe(presupuesto, use_container_width=True, hide_index=True)

        with st.form("form_presupuesto", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            categoria = c1.text_input("Categoría")
            tipo = c2.selectbox("Tipo", ["ingreso", "egreso"])
            monto = c3.number_input("Monto", 0.0)

            c4, c5 = st.columns(2)
            meta_kpi = c4.number_input("Meta KPI", 0.0)
            notas = c5.text_input("Notas")

            submit = st.form_submit_button("Guardar")

        if submit:
            with db_transaction() as conn:
                guardar_presupuesto_operativo(
                    conn,
                    periodo=periodo,
                    categoria=categoria,
                    tipo=tipo,
                    monto_presupuestado_usd=float(monto),
                    meta_kpi_usd=float(meta_kpi),
                    usuario=usuario,
                    notas=notas,
                )
            st.success("Guardado")
            st.rerun()

        st.subheader("Resumen")
        st.json(resumen)

    # =========================
    # INGRESOS (NUEVO)
    # =========================
    with tabs[2]:
        st.subheader("📈 Proyección de ingresos")

        ingresos_df = _placeholder_df(["linea", "cantidad", "precio", "total"])

        with st.form("form_ingresos"):
            c1, c2, c3 = st.columns(3)
            linea = c1.text_input("Línea negocio")
            cantidad = c2.number_input("Cantidad", 0)
            precio = c3.number_input("Precio", 0.0)

            if st.form_submit_button("Agregar"):
                total = cantidad * precio
                st.success(f"Ingreso estimado: ${total:,.2f}")

        st.dataframe(ingresos_df, use_container_width=True)

    # =========================
    # COSTOS
    # =========================
    with tabs[3]:
        st.subheader("💸 Costos y gastos")

        costos_df = _placeholder_df(["categoria", "tipo", "monto"])

        with st.form("form_costos"):
            c1, c2, c3 = st.columns(3)
            categoria = c1.text_input("Categoría")
            tipo = c2.selectbox("Tipo", ["fijo", "variable"])
            monto = c3.number_input("Monto", 0.0)

            if st.form_submit_button("Agregar costo"):
                st.success("Costo registrado")

        st.dataframe(costos_df, use_container_width=True)

    # =========================
    # KPIs
    # =========================
    with tabs[4]:
        st.subheader("📊 Indicadores financieros")

        ingresos = float(resumen.get("ingresos_totales_usd", 0))
        egresos = float(resumen.get("egresos_totales_usd", 0))
        utilidad = ingresos - egresos

        k1, k2, k3 = st.columns(3)
        k1.metric("Ingresos", f"$ {ingresos:,.2f}")
        k2.metric("Egresos", f"$ {egresos:,.2f}")
        k3.metric("Utilidad", f"$ {utilidad:,.2f}")

        if ingresos > 0:
            margen = (utilidad / ingresos) * 100
            st.metric("Margen (%)", f"{margen:.2f}%")

    # =========================
    # ALERTAS
    # =========================
    with tabs[5]:
        st.subheader("🚨 Alertas financieras")

        st.dataframe(alertas, use_container_width=True, hide_index=True)

        st.download_button(
            "Exportar alertas",
            alertas.to_csv(index=False).encode(),
            f"alertas_{periodo}.csv",
        )

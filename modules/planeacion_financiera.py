from __future__ import annotations

from datetime import date

import streamlit as st

from database.connection import db_transaction
from services.planeacion_financiera_service import (
    calcular_flujo_caja_proyectado,
    generar_alertas_gerenciales,
    guardar_presupuesto_operativo,
    listar_presupuesto_operativo,
    resumen_presupuesto_operativo,
)


def render_planeacion_financiera(usuario: str) -> None:
    st.title("📅 Presupuesto operativo y flujo proyectado")
    st.caption("Planeación financiera incremental: presupuesto, proyección 7/15/30 días y alertas gerenciales.")

    periodo_default = date.today().strftime("%Y-%m")
    periodo = st.text_input("Período (YYYY-MM)", value=periodo_default)

    with db_transaction() as conn:
        resumen = resumen_presupuesto_operativo(conn, periodo=periodo)
        flujo = calcular_flujo_caja_proyectado(conn)
        alertas = generar_alertas_gerenciales(conn, periodo=periodo)
        presupuesto = listar_presupuesto_operativo(conn, periodo=periodo)

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Saldo actual", f"$ {float(flujo.iloc[0]['saldo_actual_usd']) if not flujo.empty else 0:,.2f}")
    c2.metric("Flujo proyectado 30d", f"$ {float(flujo.iloc[-1]['flujo_proyectado_usd']) if not flujo.empty else 0:,.2f}")
    c3.metric("Pagos próximos 30d", f"$ {float(flujo.iloc[-1]['pagos_proximos_usd']) if not flujo.empty else 0:,.2f}")
    c4.metric("Cobros esperados 30d", f"$ {float(flujo.iloc[-1]['cobros_esperados_usd']) if not flujo.empty else 0:,.2f}")
    c5.metric("Desviación egresos", f"$ {float(resumen['desviacion_egresos_usd']):,.2f}")

    tab1, tab2, tab3 = st.tabs(["Proyección de caja", "Presupuesto", "Alertas"])

    with tab1:
        st.subheader("Flujo de caja proyectado")
        st.dataframe(flujo, use_container_width=True, hide_index=True)
        st.download_button(
            "Exportar proyección CSV",
            data=flujo.to_csv(index=False).encode("utf-8"),
            file_name=f"flujo_proyectado_{periodo}.csv",
            mime="text/csv",
        )

    with tab2:
        st.subheader("Resumen presupuestario")
        st.json(resumen)
        st.dataframe(presupuesto, use_container_width=True, hide_index=True)

        with st.form("form_presupuesto", clear_on_submit=True):
            f1, f2, f3 = st.columns(3)
            categoria = f1.text_input("Categoría", value="operacion_general")
            tipo = f2.selectbox("Tipo", ["ingreso", "egreso"])
            monto = f3.number_input("Monto presupuesto USD", min_value=0.0, value=0.0, step=100.0)
            f4, f5 = st.columns(2)
            meta_kpi = f4.number_input("Meta KPI USD", min_value=0.0, value=0.0, step=100.0)
            notas = f5.text_input("Notas")
            submit = st.form_submit_button("Guardar presupuesto")

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
            st.success("Presupuesto guardado correctamente.")
            st.rerun()

    with tab3:
        st.subheader("Alertas operativas y financieras")
        st.dataframe(alertas, use_container_width=True, hide_index=True)
        st.download_button(
            "Exportar alertas CSV",
            data=alertas.to_csv(index=False).encode("utf-8"),
            file_name=f"alertas_gerenciales_{periodo}.csv",
            mime="text/csv",
        )

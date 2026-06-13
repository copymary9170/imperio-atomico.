from __future__ import annotations

import streamlit as st

from services.estado_resultados_service import estado_resultados_dataframe, generar_estado_resultados


def render_estado_resultados(usuario: str) -> None:
    st.subheader("📊 Estado de resultados")
    st.caption("Resumen básico para ver ventas, costos directos, gastos, utilidad estimada y saldos pendientes.")

    c1, c2 = st.columns(2)
    fecha_desde = c1.date_input("Desde", value=None)
    fecha_hasta = c2.date_input("Hasta", value=None)
    desde = fecha_desde.isoformat() if fecha_desde else ""
    hasta = fecha_hasta.isoformat() if fecha_hasta else ""

    data = generar_estado_resultados(desde, hasta)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Ventas", f"${data['ventas_usd']:,.2f}")
    m2.metric("Costo directo", f"${data['costo_directo_usd']:,.2f}")
    m3.metric("Utilidad bruta", f"${data['utilidad_bruta_usd']:,.2f}")
    m4.metric("Utilidad estimada", f"${data['utilidad_estimada_usd']:,.2f}")

    m5, m6 = st.columns(2)
    m5.metric("Por cobrar", f"${data['cuentas_por_cobrar_pendiente_usd']:,.2f}")
    m6.metric("Por pagar", f"${data['cuentas_por_pagar_pendiente_usd']:,.2f}")

    df = estado_resultados_dataframe(desde, hasta)
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.info("Este reporte es estimado: mejora cuando ventas, gastos, compras, cuentas por cobrar y facturas de compra estén bien registrados.")
    st.caption(f"Usuario: {usuario}")

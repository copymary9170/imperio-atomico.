from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from services.rentabilidad_service import obtener_opciones_filtro, obtener_resumen_rentabilidad


def _render_metricas(metricas: dict[str, float]) -> None:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Ingreso vendido total", f"$ {metricas['ingreso_vendido_total_usd']:,.2f}")
    c2.metric("Costo real total", f"$ {metricas['costo_real_total_usd']:,.2f}")
    c3.metric("Utilidad bruta total", f"$ {metricas['utilidad_bruta_total_usd']:,.2f}")
    c4.metric("Margen promedio real", f"{metricas['margen_promedio_real_pct']:,.2f}%")
    c5.metric("Desviación promedio", f"$ {metricas['desviacion_promedio_vs_estimado_usd']:,.2f}")

    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Ingreso estimado total", f"$ {metricas['ingreso_estimado_total_usd']:,.2f}")
    d2.metric("Costo estimado total", f"$ {metricas['costo_estimado_total_usd']:,.2f}")
    d3.metric("Utilidad estimada total", f"$ {metricas['utilidad_estimada_total_usd']:,.2f}")
    d4.metric("Margen promedio estimado", f"{metricas['margen_promedio_estimado_pct']:,.2f}%")


def _download_csv_button(nombre: str, df: pd.DataFrame, filename: str) -> None:
    st.download_button(
        nombre,
        data=df.to_csv(index=False).encode("utf-8"),
        file_name=filename,
        mime="text/csv",
        use_container_width=True,
    )


def render_rentabilidad(usuario: str) -> None:
    st.title("📈 Rentabilidad analítica")
    st.caption(
        "Vista gerencial basada en costeo real para identificar márgenes, desviaciones vs estimado y oportunidades de mejora."
    )

    opciones = obtener_opciones_filtro()

    f1, f2, f3, f4, f5 = st.columns(5)
    fecha_desde = f1.date_input("Desde", value=date.today() - timedelta(days=90))
    fecha_hasta = f2.date_input("Hasta", value=date.today())
    tipo_proceso = f3.selectbox("Tipo de proceso", ["Todos"] + opciones["tipos_proceso"])
    estado = f4.selectbox("Estado", ["Todos"] + opciones["estados"])
    usuario_sel = f5.selectbox("Usuario", ["Todos"] + opciones["usuarios"], index=0)

    data = obtener_resumen_rentabilidad(
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        tipo_proceso=None if tipo_proceso == "Todos" else tipo_proceso,
        estado=None if estado == "Todos" else estado,
        usuario=None if usuario_sel == "Todos" else usuario_sel,
    )

    metricas = data["metricas"]
    if metricas["total_trabajos"] == 0:
        st.info("No hay costeos ejecutados/cerrados para los filtros seleccionados.")
        return

    _render_metricas(metricas)

    st.divider()
    tab1, tab2, tab3, tab4 = st.tabs(
        [
            "Rentabilidad por proceso",
            "Rankings de trabajos",
            "Desviaciones estimado vs real",
            "Base operativa",
        ]
    )

    with tab1:
        resumen_proceso = data["rentabilidad_por_proceso"]
        st.subheader("Rentabilidad por tipo de proceso")
        st.dataframe(resumen_proceso, use_container_width=True, hide_index=True)
        _download_csv_button(
            "Exportar rentabilidad por proceso (CSV)", resumen_proceso, "rentabilidad_por_proceso.csv"
        )

        if not resumen_proceso.empty:
            st.bar_chart(resumen_proceso.set_index("tipo_proceso")[["utilidad_bruta_usd", "desviacion_promedio_usd"]])

        composicion = data["composicion_real"]
        st.subheader("Composición del costo real por categoría")
        st.dataframe(composicion, use_container_width=True, hide_index=True)
        _download_csv_button("Exportar composición costo real (CSV)", composicion, "composicion_costo_real.csv")

    with tab2:
        mejores = data["trabajos_mas_rentables"]
        peores = data["trabajos_menos_rentables"]

        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Trabajos más rentables")
            st.dataframe(mejores, use_container_width=True, hide_index=True)
            _download_csv_button("Exportar top rentables (CSV)", mejores, "trabajos_mas_rentables.csv")
        with c2:
            st.subheader("Trabajos menos rentables")
            st.dataframe(peores, use_container_width=True, hide_index=True)
            _download_csv_button("Exportar top menos rentables (CSV)", peores, "trabajos_menos_rentables.csv")

    with tab3:
        desviaciones = data["mayores_desviaciones"]
        st.subheader("Mayores desviaciones estimado vs real")
        st.dataframe(desviaciones, use_container_width=True, hide_index=True)
        _download_csv_button("Exportar desviaciones (CSV)", desviaciones, "desviaciones_estimado_real.csv")

        if not desviaciones.empty:
            st.bar_chart(desviaciones.set_index("id")[["diferencia_vs_estimado_usd", "diferencia_utilidad_vs_estimado_usd"]])

    with tab4:
        base = data["trabajos"]
        st.subheader("Base de costeos para análisis")
        st.dataframe(base, use_container_width=True, hide_index=True)
        _download_csv_button("Exportar base operativa (CSV)", base, "rentabilidad_base_operativa.csv")

    st.caption(f"Consulta ejecutada por: {usuario}")

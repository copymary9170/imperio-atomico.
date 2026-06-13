from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from services.presupuesto_equilibrio_service import (
    CATEGORIAS_PRESUPUESTO,
    calcular_punto_equilibrio,
    guardar_meta_equilibrio,
    guardar_presupuesto_linea,
    listar_metas_equilibrio,
    listar_presupuesto,
    resumen_presupuesto,
)


def _periodo_actual() -> str:
    hoy = date.today()
    return f"{hoy.year}-{hoy.month:02d}"


def render_presupuesto_equilibrio(usuario: str) -> None:
    st.title("📅 Presupuesto y punto de equilibrio")
    st.caption("Planifica cuánto esperas vender, cuánto puedes gastar y cuánto necesita vender Copy Mary para cubrir costos y ganar.")

    tab_presupuesto, tab_equilibrio, tab_historial = st.tabs(["📅 Presupuesto mensual", "⚖️ Punto de equilibrio", "Historial"])

    with tab_presupuesto:
        periodo = st.text_input("Periodo", value=_periodo_actual(), help="Formato recomendado: AAAA-MM, por ejemplo 2026-06")
        resumen = resumen_presupuesto(periodo)
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Ingresos estimados", f"${resumen['estimado_ingresos']:,.2f}")
        m2.metric("Egresos estimados", f"${resumen['estimado_egresos']:,.2f}")
        m3.metric("Resultado estimado", f"${resumen['resultado_estimado']:,.2f}")
        m4.metric("Resultado real", f"${resumen['resultado_real']:,.2f}")

        with st.form("form_presupuesto_linea"):
            c1, c2, c3 = st.columns(3)
            categoria = c1.selectbox("Categoría", CATEGORIAS_PRESUPUESTO)
            concepto = c2.text_input("Concepto", placeholder="Ej: ventas de impresiones, internet, papel, Adobe")
            monto_estimado = c3.number_input("Monto estimado USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            c4, c5 = st.columns([1, 2])
            monto_real = c4.number_input("Monto real USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            notas = c5.text_input("Notas")
            submitted = st.form_submit_button("Agregar línea al presupuesto", use_container_width=True)
        if submitted:
            try:
                linea_id = guardar_presupuesto_linea(usuario=usuario, periodo=periodo, categoria=categoria, concepto=concepto, monto_estimado_usd=float(monto_estimado), monto_real_usd=float(monto_real), notas=notas)
                st.success(f"Línea agregada: #{linea_id}")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo guardar: {exc}")

        df = listar_presupuesto(periodo)
        if df.empty:
            st.info("Aún no hay presupuesto para este periodo.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_equilibrio:
        st.markdown("#### Calculadora de ventas mínimas")
        c1, c2, c3, c4 = st.columns(4)
        gastos_fijos = c1.number_input("Gastos fijos USD", min_value=0.0, value=30.0, step=1.0, format="%.4f")
        gastos_variables = c2.number_input("Gastos variables USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
        margen = c3.number_input("Margen promedio %", min_value=0.01, value=40.0, step=1.0, format="%.4f")
        ganancia_objetivo = c4.number_input("Ganancia objetivo USD", min_value=0.0, value=100.0, step=1.0, format="%.4f")

        calc = calcular_punto_equilibrio(gastos_fijos, gastos_variables, margen, ganancia_objetivo)
        m1, m2, m3 = st.columns(3)
        m1.metric("Gastos totales", f"${calc['gastos_totales_usd']:,.2f}")
        m2.metric("Ventas para no perder", f"${calc['ventas_equilibrio_usd']:,.2f}")
        m3.metric("Ventas para meta", f"${calc['ventas_meta_usd']:,.2f}")

        st.info("Ejemplo: si tu margen promedio es 40%, no todo lo vendido es ganancia. Para cubrir $100 de gastos necesitas vender aproximadamente $250.")

        with st.form("form_guardar_equilibrio"):
            periodo_eq = st.text_input("Periodo meta", value=_periodo_actual())
            notas_eq = st.text_area("Notas de la meta")
            submitted_eq = st.form_submit_button("Guardar meta de equilibrio", use_container_width=True)
        if submitted_eq:
            try:
                meta_id = guardar_meta_equilibrio(usuario=usuario, periodo=periodo_eq, gastos_fijos_usd=float(gastos_fijos), gastos_variables_usd=float(gastos_variables), margen_promedio_pct=float(margen), ganancia_objetivo_usd=float(ganancia_objetivo), notas=notas_eq)
                st.success(f"Meta guardada: #{meta_id}")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo guardar la meta: {exc}")

    with tab_historial:
        st.markdown("#### Presupuestos registrados")
        df_all = listar_presupuesto("")
        if df_all.empty:
            st.info("Sin líneas de presupuesto.")
        else:
            st.dataframe(df_all, use_container_width=True, hide_index=True)

        st.markdown("#### Metas de equilibrio")
        metas = listar_metas_equilibrio()
        if metas.empty:
            st.info("Sin metas guardadas.")
        else:
            st.dataframe(metas, use_container_width=True, hide_index=True)

    st.caption(f"Usuario: {usuario}")

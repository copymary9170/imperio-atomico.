from __future__ import annotations

import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def _render_rrhh_focus() -> None:
    st.markdown("### 🎯 Focos de mejora inmediata")
    st.markdown(
        "- **Digitalizar altas y bajas** con checklist de documentación, equipo y permisos.\n"
        "- **Controlar asistencia y novedades** con cierres semanales para evitar ajustes tardíos.\n"
        "- **Vincular desempeño y compensación** con metas operativas por área."
    )

    st.markdown("### 📊 Indicadores recomendados")
    kpi_1, kpi_2, kpi_3 = st.columns(3)
    kpi_1.metric("Rotación mensual", "≤ 3%", "Meta")
    kpi_2.metric("Ausentismo", "≤ 2.5%", "Meta")
    kpi_3.metric("Cobertura de capacitación", ">= 90%", "Meta")

    st.caption(
        "Estos indicadores sirven como punto de partida para formalizar un tablero de RRHH conectado con producción, seguridad y finanzas."
    )



def _render_rrhh_implementation_plan() -> None:
    st.markdown("### 🗺️ Plan sugerido de implementación (90 días)")
    st.markdown(
        "1. **Semanas 1-2:** estandarizar catálogo de empleados, turnos, centros de costo y roles.\n"
        "2. **Semanas 3-6:** activar procesos de ingreso/baja, asistencia y novedades salariales.\n"
        "3. **Semanas 7-10:** integrar tableros de productividad por área y alertas de ausentismo.\n"
        "4. **Semanas 11-12:** cerrar piloto, ajustar reglas y desplegar a toda la empresa."
    )
    st.info("Resultado esperado: menos carga administrativa y decisiones de personal más rápidas y trazables.")



def render_rrhh(usuario):
    st.title("👨‍💼 RRHH")

    overview_tab, roadmap_tab = st.tabs(["📌 Blueprint", "🚀 Mejora RRHH"])

    with overview_tab:
        render_module_blueprint("rrhh", usuario)

    with roadmap_tab:
        st.markdown("## Hoja de ruta para fortalecer RRHH")
        if usuario:
            st.caption(f"Recomendaciones personalizadas para {usuario}.")
        _render_rrhh_focus()
        _render_rrhh_implementation_plan()

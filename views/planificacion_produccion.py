import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_planificacion_produccion(usuario):
    st.title("🗓️ Planificación de producción")
    render_module_blueprint("planificacion_produccion", usuario)

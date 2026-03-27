import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_rutas_produccion(usuario):
    st.title("🧭 Rutas de producción")
    render_module_blueprint("rutas_produccion", usuario)

import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_mantenimiento_activos(usuario):
    st.title("🛠️ Mantenimiento de activos")
    render_module_blueprint("mantenimiento_activos", usuario)

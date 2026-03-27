import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_control_calidad(usuario):
    st.title("✅ Control de calidad")
    render_module_blueprint("control_calidad", usuario)

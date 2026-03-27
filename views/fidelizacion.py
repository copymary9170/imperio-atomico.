import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_fidelizacion(usuario):
    st.title("⭐ Fidelización")
    render_module_blueprint("fidelizacion", usuario)

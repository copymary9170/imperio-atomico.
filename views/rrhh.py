import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_rrhh(usuario):
    st.title("👨‍💼 RRHH")
    render_module_blueprint("rrhh", usuario)

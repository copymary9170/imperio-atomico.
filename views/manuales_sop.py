import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_manuales_sop(usuario):
    st.title("📘 Manuales / SOP")
    render_module_blueprint("manuales_sop", usuario)

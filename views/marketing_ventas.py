import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_marketing_ventas(usuario):
    st.title("📣 Marketing / Ventas")
    render_module_blueprint("marketing_ventas", usuario)

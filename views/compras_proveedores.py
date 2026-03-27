import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_compras_proveedores(usuario):
    st.title("🚚 Compras / Proveedores")
    render_module_blueprint("compras_proveedores", usuario)

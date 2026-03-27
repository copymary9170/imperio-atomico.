import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_seguridad_roles(usuario):
    st.title("🔐 Seguridad / Roles")
    render_module_blueprint("seguridad_roles", usuario)

import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_mermas_desperdicio(usuario):
    st.title("♻️ Mermas y desperdicio")
    render_module_blueprint("mermas_desperdicio", usuario)

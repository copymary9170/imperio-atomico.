import streamlit as st

from modules.erp_nuevos_modulos import render_module_blueprint


def render_costeo_industrial(usuario):
    st.title("🧮 Costos / Costeo industrial")
    render_module_blueprint("costeo_industrial", usuario)

import streamlit as st
from modules.produccion import render_produccion_manual


def render_produccion_manual(usuario):
    st.title("🎨 Producción Manual")

    render_produccion_manual(usuario)

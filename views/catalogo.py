import streamlit as st

from modules.catalogo import render_catalogo_hub


def render_catalogo(usuario):
    st.title("🛍️ Catálogo")
    render_catalogo_hub(usuario)

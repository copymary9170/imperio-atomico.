import streamlit as st
from modules.cmyk import render_cmyk


def render_cmyk_view(usuario: str):

    st.title("🎨 Análisis CMYK")

    render_cmyk(usuario)

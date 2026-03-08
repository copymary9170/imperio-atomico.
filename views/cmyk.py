import streamlit as st
from modules.cmyk import render_cmyk


def render_cmyk(usuario):
    st.title("🎨 Análisis CMYK")

    render_cmyk(usuario)

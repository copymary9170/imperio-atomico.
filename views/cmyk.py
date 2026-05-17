import streamlit as st

from modules.cmyk_engine import render_cmyk as render_cmyk_modulo
from views.cmyk_control import render_cmyk_control


def render_cmyk(usuario):
    st.title("🎨 CMYK")

    tab_motor, tab_control = st.tabs([
        "Motor CMYK",
        "📊 Control CMYK",
    ])

    with tab_motor:
        render_cmyk_modulo(usuario)

    with tab_control:
        render_cmyk_control(usuario)

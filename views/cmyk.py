import streamlit as st

from modules.cmyk_engine import render_cmyk as render_cmyk_modulo
from views.cmyk_control import render_cmyk_control
from views.contadores_clics import render_contadores_clics


def render_cmyk(usuario):
    st.title("🎨 CMYK")

    tab_motor, tab_control, tab_contadores = st.tabs([
        "Motor CMYK",
        "📊 Control CMYK",
        "🖨️ Contadores y clics",
    ])

    with tab_motor:
        render_cmyk_modulo(usuario)

    with tab_control:
        render_cmyk_control(usuario)

    with tab_contadores:
        render_contadores_clics(usuario)

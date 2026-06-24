import streamlit as st

from modules.cotizaciones import render_cotizaciones as cotizaciones_module
from views.costeo_integral import render_costeo_integral


def render_cotizaciones(usuario):
    st.title("📝 Cotizaciones")
    tab_integral, tab_legacy = st.tabs(["🔗 Costeo integral", "Cotizaciones actuales"])
    with tab_integral:
        render_costeo_integral(usuario)
    with tab_legacy:
        cotizaciones_module(usuario)

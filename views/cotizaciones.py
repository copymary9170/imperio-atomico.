import streamlit as st

from modules.cotizaciones import render_cotizaciones as cotizaciones_module
from views.costeo_integral import render_costeo_integral
from views.cotizador_archivo import render_cotizador_archivo


def render_cotizaciones(usuario):
    st.title("📝 Cotizaciones")
    tab_file, tab_integral, tab_legacy = st.tabs([
        "📄 Cotizar desde archivo",
        "🔗 Costeo integral",
        "Cotizaciones actuales",
    ])
    with tab_file:
        render_cotizador_archivo(usuario)
    with tab_integral:
        render_costeo_integral(usuario)
    with tab_legacy:
        cotizaciones_module(usuario)

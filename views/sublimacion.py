import streamlit as st

from modules.sublimacion import render_sublimacion as sublimacion_module
from views.sublimacion_control import render_sublimacion_control


def render_sublimacion(usuario):
    st.title("🔥 Sublimación")
    st.caption("Consumo de tinta y material, capacidad instalada, tiempos, reprocesos y calidad del acabado.")

    tab_operacion, tab_control = st.tabs([
        "Operación sublimación",
        "📊 Control ejecutivo",
    ])

    with tab_operacion:
        sublimacion_module(usuario)

    with tab_control:
        render_sublimacion_control(usuario)

import streamlit as st

from modules.sublimacion import render_sublimacion as sublimacion_module


def render_sublimacion(usuario):
    st.title("🔥 Sublimación")
    st.caption("Consumo de tinta y material, capacidad instalada, tiempos, reprocesos y calidad del acabado.")

    sublimacion_module(usuario)

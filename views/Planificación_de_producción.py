import streamlit as st
from modules.produccion import render_produccion as produccion_module


def render_produccion(usuario: str) -> None:
    # ============================================================
    # TITULO PRINCIPAL
    # ============================================================
    st.title("🗓️ Planificación de producción")

    st.caption(
        "Organiza, programa y controla tu producción: órdenes, tiempos, costos y ejecución."
    )

    # ============================================================
    # RENDER MODULO
    # ============================================================
    try:
        produccion_module(usuario)
    except Exception as e:
        st.error("Error cargando el módulo de producción")
        st.exception(e)

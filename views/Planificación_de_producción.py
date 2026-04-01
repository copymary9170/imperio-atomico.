import streamlit as st

import modules.Planificación_de_producción as planificacion_produccion_module


def render_produccion(usuario):
    st.title("🗓️ Planificación de producción")
    planificacion_produccion_module.render_produccion(usuario)

import streamlit as st

import modules.Planificación_de_producción as planificacion_produccion_module


def render_planificacion_produccion(usuario: str) -> None:
    st.title("🗓️ Planificación de producción")
    planificacion_produccion_module.render_produccion(usuario)


def render_produccion(usuario: str) -> None:
    """Compatibilidad con importaciones antiguas."""
    render_planificacion_produccion(usuario)

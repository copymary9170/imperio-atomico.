port streamlit as st

from modules.control_calidad import render_control_calidad as control_calidad_module


def render_control_calidad(usuario: str) -> None:
    st.title("✅ Control de calidad")
    control_calidad_module(usuario=

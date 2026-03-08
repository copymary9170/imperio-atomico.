import streamlit as st
from modules.diagnostico import render_diagnostico as diagnostico_module


def render_diagnostico(usuario):
    st.title("🧠 Diagnóstico IA")

    diagnostico_module(usuario)

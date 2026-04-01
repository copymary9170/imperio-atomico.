import streamlit as st
from modules.Planificación_de_producción import render_produccion as produccion_module


def render_produccion(usuario):
    st.title("🗓️ Planificación de producción")
    produccion_module(usuario)

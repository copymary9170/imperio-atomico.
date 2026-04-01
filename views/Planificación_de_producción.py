import streamlit as st
from modules.produccion import render_produccion as produccion_module


def render_produccion(usuario):
    st.title("🗓️ Planificación de producción")
    produccion_module(usuario)

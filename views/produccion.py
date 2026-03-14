import streamlit as st
from modules.produccion import render_produccion_manual as produccion_module


def render_produccion(usuario):
    st.title("Producción")
    produccion_module(usuario)

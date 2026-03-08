import streamlit as st
from modules.ventas import render_ventas


def render_venta_directa(usuario):
    st.title("🛒 Venta Directa")

    render_ventas(usuario)

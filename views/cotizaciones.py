import streamlit as st
from modules.cotizaciones import render_cotizaciones


def render_cotizaciones(usuario):
    st.title("📝 Cotizaciones")

    render_cotizaciones(usuario)

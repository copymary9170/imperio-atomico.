import streamlit as st
from modules.cotizaciones import render_cotizaciones as cotizaciones_module


def render_cotizaciones(usuario):

    st.title("📝 Cotizaciones")

    cotizaciones_module(usuario)

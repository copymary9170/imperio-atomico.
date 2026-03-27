import streamlit as st

from modules.conciliacion_bancaria import render_conciliacion_bancaria as render_conciliacion_bancaria_module


def render_conciliacion_bancaria(usuario):
    st.title("🏛️ Conciliación bancaria")
    render_conciliacion_bancaria_module(usuario)

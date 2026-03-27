import streamlit as st

from modules.impuestos import render_impuestos as render_impuestos_module


def render_impuestos(usuario):
    st.title("🧾 Impuestos")
    render_impuestos_module(usuario)

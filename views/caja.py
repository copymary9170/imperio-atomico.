import streamlit as st
from modules.caja import render_caja as caja_module


def render_caja(usuario):
    st.title("🏁 Cierre de Caja")

    caja_module(usuario)

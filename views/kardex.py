import streamlit as st
from modules.inventario import render_kardex


def render_kardex(usuario):
    st.title("📊 Kardex")

    render_kardex(usuario)

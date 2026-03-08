import streamlit as st
from modules.inventario import render_kardex


def render_kardex_view(usuario: str):

    st.title("📊 Kardex")

    render_kardex(usuario)

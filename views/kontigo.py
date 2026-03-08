import streamlit as st
from modules.kontigo import render_kontigo


def render_kontigo(usuario):
    st.title("💳 Kontigo")

    render_kontigo(usuario)

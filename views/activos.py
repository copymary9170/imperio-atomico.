import streamlit as st
from modules.activos import render_activos as activos_module


def render_activos(usuario: str):

    st.title("🏗️ Activos")

    activos_module(usuario)

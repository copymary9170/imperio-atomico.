import streamlit as st
from modules.sublimacion import render_sublimacion as sublimacion_module


def render_sublimacion(usuario):
    st.title("🔥 Sublimación")

    sublimacion_module(usuario)

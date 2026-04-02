import streamlit as st
from modules.produccion_manual import render_produccion_manual as produccion_module


def render_produccion_manual(usuario):

    st.title("🎨 Producción Manual")

    produccion_module(usuario)

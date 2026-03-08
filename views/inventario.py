import streamlit as st
from modules.inventario import render_inventario as inventario_module


def render_inventario(usuario):
    st.title("📦 Inventario")

    inventario_module(usuario)

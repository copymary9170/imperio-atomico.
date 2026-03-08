import streamlit as st
from modules.clientes import render_clientes as clientes_module


def render_clientes(usuario):
    st.title("👥 Clientes")

    clientes_module(usuario)

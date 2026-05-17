import streamlit as st
from modules.clientes import render_clientes as clientes_module
from views.clientes_inteligencia import render_clientes_inteligencia


def render_clientes(usuario):
    st.title("👥 Clientes")

    tab_operativo, tab_inteligencia = st.tabs([
        "Clientes operativos",
        "🧠 Inteligencia comercial",
    ])

    with tab_operativo:
        clientes_module(usuario)

    with tab_inteligencia:
        render_clientes_inteligencia(usuario)

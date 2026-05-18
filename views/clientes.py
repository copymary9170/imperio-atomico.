import streamlit as st
from modules.clientes import render_clientes as clientes_module
from views.clientes_inteligencia import render_clientes_inteligencia
from views.crm_avanzado import render_crm_avanzado


def render_clientes(usuario):
    st.title("👥 Clientes")

    tab_crm, tab_operativo, tab_inteligencia = st.tabs([
        "🤝 CRM / Prospectos",
        "Clientes operativos",
        "🧠 Inteligencia comercial",
    ])

    with tab_crm:
        render_crm_avanzado(usuario)

    with tab_operativo:
        clientes_module(usuario)

    with tab_inteligencia:
        render_clientes_inteligencia(usuario)

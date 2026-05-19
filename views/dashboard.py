import streamlit as st
from modules.dashboard import render_dashboard as dashboard_module
from views.modo_supervisor import render_modo_supervisor


def render_dashboard():
    st.title("📊 Panel de control")

    usuario = st.session_state.get("usuario", "Sistema")
    tab_supervisor, tab_dashboard = st.tabs([
        "🧑‍💼 Modo Supervisor",
        "Dashboard operativo",
    ])

    with tab_supervisor:
        render_modo_supervisor(usuario)

    with tab_dashboard:
        dashboard_module()

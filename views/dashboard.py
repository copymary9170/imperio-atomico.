import streamlit as st
from modules.dashboard import render_dashboard as dashboard_module
from views.modo_supervisor import render_modo_supervisor


def render_dashboard():
    """Dashboard operativo interno del Panel de control.

    No repite el título principal del Panel de control; app.py ya lo presenta
    como pestaña dentro de 📊 Panel de control.
    """
    usuario = st.session_state.get("usuario", "Sistema")

    tab_supervisor, tab_analitica = st.tabs([
        "🧑‍💼 Supervisor diario",
        "📈 Analítica financiera",
    ])

    with tab_supervisor:
        render_modo_supervisor(usuario)

    with tab_analitica:
        dashboard_module()

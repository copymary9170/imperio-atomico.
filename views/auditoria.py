import streamlit as st
from modules.auditoria import render_auditoria as auditoria_module
from views.auditoria_operativa import render_auditoria_operativa


def render_auditoria(usuario):
    st.title("📊 Auditoría y Métricas")

    tab_metricas, tab_bitacora = st.tabs([
        "Métricas generales",
        "🧾 Bitácora operativa",
    ])

    with tab_metricas:
        auditoria_module(usuario)

    with tab_bitacora:
        render_auditoria_operativa(usuario)

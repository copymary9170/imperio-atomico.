import streamlit as st
from modules.auditoria import render_auditoria


def render_auditoria(usuario):
    st.title("📊 Auditoría y Métricas")

    render_auditoria()

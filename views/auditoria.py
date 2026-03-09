import streamlit as st
from modules.auditoria import render_auditoria as auditoria_module


def render_auditoria(usuario):

    st.title("📊 Auditoría y Métricas")

    auditoria_module()

import streamlit as st
from modules.corte import render_corte as corte_module


def render_corte(usuario: str) -> None:
    # Configuración visual del módulo
    st.markdown("## ✂️ Corte Industrial")
    st.caption("Gestión de análisis, órdenes, ejecución, merma y trazabilidad de corte.")

    # Contenedor principal (mejor separación visual)
    with st.container():
        corte_module(usuario)

import streamlit as st

from modules.corte import render_corte as corte_module
from views.corte_control import render_corte_control


def render_corte(usuario: str) -> None:
    st.markdown("## ✂️ Corte Industrial")
    st.caption("Gestión de análisis, órdenes, ejecución, merma y trazabilidad de corte.")

    tab_operacion, tab_control = st.tabs([
        "Operación corte",
        "📊 Control ejecutivo",
    ])

    with tab_operacion:
        corte_module(usuario)

    with tab_control:
        render_corte_control(usuario)

import streamlit as st

from modules.produccion_manual import render_produccion_manual as produccion_module
from modules.procesos import render_otros_procesos


def render_produccion_manual(usuario):
    st.subheader("🎨 Producción, acabados y ensamblaje")
    st.caption(
        "Gestiona en un mismo flujo la elaboración manual, los acabados especiales "
        "y el armado final del producto."
    )

    tab_produccion, tab_acabados = st.tabs(
        ["🎨 Producción manual", "✨ Acabados y ensamblaje"]
    )

    with tab_produccion:
        produccion_module(usuario)

    with tab_acabados:
        render_otros_procesos(usuario, integrado_en_produccion=True)

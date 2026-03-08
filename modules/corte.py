from __future__ import annotations

import streamlit as st
import pandas as pd


def render_corte(usuario: str):

    st.title("✂️ Corte Industrial")

    st.info("Gestión de trabajos de corte.")

    material = st.text_input("Material")

    ancho = st.number_input("Ancho (cm)", min_value=0.0)

    alto = st.number_input("Alto (cm)", min_value=0.0)

    cantidad = st.number_input("Cantidad", min_value=1)

    if st.button("Calcular corte"):

        area = ancho * alto
        total = area * cantidad

        st.metric("Área por pieza", f"{area:.2f} cm²")
        st.metric("Área total", f"{total:.2f} cm²")

        df = pd.DataFrame({
            "Material": [material],
            "Ancho": [ancho],
            "Alto": [alto],
            "Cantidad": [cantidad],
            "Área total": [total]
        })

        st.dataframe(df, use_container_width=True)

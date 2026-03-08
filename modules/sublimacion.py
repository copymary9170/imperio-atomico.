from __future__ import annotations

import streamlit as st
import pandas as pd


def render_sublimacion(usuario: str):

    st.title("🔥 Sublimación Industrial")

    st.info("Calculadora básica de trabajos de sublimación")

    producto = st.text_input("Producto")

    ancho = st.number_input("Ancho (cm)", min_value=0.0)
    alto = st.number_input("Alto (cm)", min_value=0.0)

    cantidad = st.number_input("Cantidad", min_value=1)

    costo_transfer = st.number_input(
        "Costo transfer unitario",
        min_value=0.0,
        value=0.20
    )

    if st.button("Calcular producción"):

        area = ancho * alto

        costo_unitario = costo_transfer

        costo_total = costo_unitario * cantidad

        st.metric("Área por pieza", f"{area:.2f} cm²")
        st.metric("Costo unitario", f"$ {costo_unitario:.2f}")
        st.metric("Costo total", f"$ {costo_total:.2f}")

        df = pd.DataFrame({
            "Producto": [producto],
            "Cantidad": [cantidad],
            "Costo unitario": [costo_unitario],
            "Costo total": [costo_total]
        })

        st.dataframe(df, use_container_width=True)

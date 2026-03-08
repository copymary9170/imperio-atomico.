# ============================================================
# PRODUCCIÓN MANUAL
# ============================================================

import streamlit as st
import pandas as pd


def render_produccion_manual(usuario: str):

    st.title("🎨 Producción Manual")

    producto = st.text_input("Producto")

    descripcion = st.text_area("Descripción del trabajo")

    cantidad = st.number_input(
        "Cantidad",
        min_value=1
    )

    costo_unitario = st.number_input(
        "Costo unitario USD",
        min_value=0.0
    )

    if st.button("Registrar producción"):

        total = cantidad * costo_unitario

        st.success("Producción registrada")

        st.metric("Costo total", f"$ {total:.2f}")

        df = pd.DataFrame({
            "Producto": [producto],
            "Cantidad": [cantidad],
            "Costo unitario": [costo_unitario],
            "Total": [total]
        })

        st.dataframe(df, use_container_width=True)

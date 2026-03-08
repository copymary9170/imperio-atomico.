from __future__ import annotations

import streamlit as st
import pandas as pd


def render_kontigo(usuario: str):

    st.title("💳 Kontigo")

    st.info("Gestión de pagos y movimientos Kontigo")

    cliente = st.text_input("Cliente")

    monto = st.number_input(
        "Monto",
        min_value=0.0
    )

    referencia = st.text_input("Referencia")

    if st.button("Registrar movimiento"):

        df = pd.DataFrame({
            "Cliente": [cliente],
            "Monto": [monto],
            "Referencia": [referencia],
            "Usuario": [usuario]
        })

        st.success("Movimiento registrado")

        st.dataframe(df, use_container_width=True)

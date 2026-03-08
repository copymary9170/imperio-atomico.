from __future__ import annotations

import streamlit as st
import pandas as pd


def render_otros_procesos(usuario: str):

    st.title("🛠️ Otros Procesos")

    st.info("Centro de procesos adicionales del ERP.")

    proceso = st.selectbox(
        "Seleccionar proceso",
        [
            "Corte simple",
            "Laminado",
            "Troquelado",
            "Empaque",
            "Otro"
        ]
    )

    descripcion = st.text_area("Descripción del proceso")

    tiempo = st.number_input(
        "Tiempo estimado (minutos)",
        min_value=0.0
    )

    costo = st.number_input(
        "Costo estimado USD",
        min_value=0.0
    )

    if st.button("Registrar proceso"):

        df = pd.DataFrame({
            "Usuario": [usuario],
            "Proceso": [proceso],
            "Descripción": [descripcion],
            "Tiempo": [tiempo],
            "Costo": [costo]
        })

        st.success("Proceso registrado")
        st.dataframe(df, use_container_width=True)

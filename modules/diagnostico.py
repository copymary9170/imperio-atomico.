from __future__ import annotations

import streamlit as st
import pandas as pd

from services.diagnostics_service import analizar_hoja_diagnostico


def render_diagnostico(usuario: str):

    st.title("🧠 Diagnóstico de Impresoras")

    st.info("Sube una hoja de diagnóstico o pega el texto OCR.")

    texto = st.text_area("Texto diagnóstico")

    capacidad = {
        "Cyan": st.number_input("Capacidad Cyan (ml)", value=70.0),
        "Magenta": st.number_input("Capacidad Magenta (ml)", value=70.0),
        "Yellow": st.number_input("Capacidad Yellow (ml)", value=70.0),
        "Black": st.number_input("Capacidad Black (ml)", value=70.0),
    }

    if st.button("Analizar diagnóstico"):

        resultado = analizar_hoja_diagnostico(
            texto_ocr=texto,
            capacidad=capacidad
        )

        st.subheader("Resultado")

        st.json(resultado["resumen"])

        df = pd.DataFrame(
            list(resultado["resultados"].items()),
            columns=["Color", "Nivel ml"]
        )

        st.dataframe(df, use_container_width=True)

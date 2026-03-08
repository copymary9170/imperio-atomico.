from __future__ import annotations

import streamlit as st
import pandas as pd


def render_cmyk(usuario: str):

    st.title("🎨 Análisis CMYK")

    st.info("Módulo de análisis de tinta CMYK")

    c1, c2, c3, c4 = st.columns(4)

    cyan = c1.number_input("Cyan %", min_value=0, max_value=100, value=0)
    magenta = c2.number_input("Magenta %", min_value=0, max_value=100, value=0)
    yellow = c3.number_input("Yellow %", min_value=0, max_value=100, value=0)
    black = c4.number_input("Black %", min_value=0, max_value=100, value=0)

    if st.button("Analizar tinta"):

        total = cyan + magenta + yellow + black

        st.metric("Carga total tinta", f"{total}%")

        df = pd.DataFrame(
            {
                "Color": ["Cyan", "Magenta", "Yellow", "Black"],
                "Porcentaje": [cyan, magenta, yellow, black],
            }
        )

        st.bar_chart(df.set_index("Color"))

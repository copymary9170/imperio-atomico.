from __future__ import annotations

import streamlit as st
from database.connection import db_transaction


def render_configuracion(usuario: str):

    st.title("⚙️ Configuración")
    st.write("Panel de configuración del sistema")

    st.divider()

    st.subheader("Parámetros del sistema")

    with db_transaction() as conn:

        rows = conn.execute(
            """
            SELECT parametro, valor
            FROM configuracion
            """
        ).fetchall()

    config = {r["parametro"]: r["valor"] for r in rows}

    tasa_bcv = st.number_input(
        "Tasa BCV",
        value=float(config.get("tasa_bcv", 36.5))
    )

    margen_impresion = st.number_input(
        "Margen impresión %",
        value=float(config.get("margen_impresion", 30))
    )

    costo_kwh = st.number_input(
        "Costo electricidad (kWh)",
        value=float(config.get("costo_kwh", 0.12))
    )

    if st.button("Guardar configuración"):

        with db_transaction() as conn:

            conn.execute(
                "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES ('tasa_bcv', ?)",
                (tasa_bcv,)
            )

            conn.execute(
                "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES ('margen_impresion', ?)",
                (margen_impresion,)
            )

            conn.execute(
                "INSERT OR REPLACE INTO configuracion (parametro, valor) VALUES ('costo_kwh', ?)",
                (costo_kwh,)
            )

        st.success("Configuración guardada")

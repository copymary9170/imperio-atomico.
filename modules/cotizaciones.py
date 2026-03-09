from __future__ import annotations

import streamlit as st
import pandas as pd
from database.connection import db_transaction


def render_cotizaciones(usuario: str):

    st.subheader("📝 Gestión de Cotizaciones")

    try:
        with db_transaction() as conn:

            rows = conn.execute(
                """
                SELECT
                    id,
                    usuario,
                    descripcion,
                    costo_estimado_usd,
                    margen_pct,
                    precio_final_usd,
                    estado,
                    fecha
                FROM cotizaciones
                ORDER BY fecha DESC
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando cotizaciones")
        st.exception(e)
        return

    if not rows:
        st.info("No hay cotizaciones registradas.")
        return

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

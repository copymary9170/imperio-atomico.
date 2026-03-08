from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction


# ============================================================
# 🔎 MÓDULO DE AUDITORÍA
# ============================================================

def render_auditoria() -> None:
    """
    Muestra los últimos registros de auditoría del sistema.
    """

    st.subheader("🔎 Auditoría del Sistema")

    try:

        with db_transaction() as conn:

            rows = conn.execute(
                """
                SELECT 
                    fecha,
                    usuario,
                    accion,
                    valor_anterior,
                    valor_nuevo
                FROM auditoria
                ORDER BY id DESC
                LIMIT 500
                """
            ).fetchall()

        # Si no hay registros
        if not rows:
            st.info("No hay registros de auditoría todavía.")
            return

        # Convertir a DataFrame para mejor visualización
        columnas = [
            "Fecha",
            "Usuario",
            "Acción",
            "Valor Anterior",
            "Valor Nuevo"
        ]

        df = pd.DataFrame(rows, columns=columnas)

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

    except Exception as e:

        st.error("Error cargando auditoría")

        st.exception(e)

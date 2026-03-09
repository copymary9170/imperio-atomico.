from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction


def render_auditoria(usuario: str):

    st.title("📊 Auditoría y Métricas")
    st.info("Registro de actividad del sistema.")

    try:

        with db_transaction() as conn:

            # verificar si existe la tabla auditoria
            table_exists = conn.execute(
                """
                SELECT name 
                FROM sqlite_master 
                WHERE type='table' AND name='auditoria'
                """
            ).fetchone()

            if not table_exists:

                st.warning("La tabla de auditoría aún no existe en la base de datos.")
                st.info("Ejecuta el schema nuevamente o reinicia la base de datos.")
                return

            rows = conn.execute(
                """
                SELECT
                    fecha,
                    usuario,
                    accion,
                    valor_anterior,
                    valor_nuevo
                FROM auditoria
                ORDER BY fecha DESC
                LIMIT 500
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando auditoría")
        st.exception(e)
        return

    if not rows:

        st.info("No hay registros de auditoría.")
        return

    df = pd.DataFrame(rows)

    buscar = st.text_input("🔎 Buscar acción")

    if buscar:

        df = df[
            df.astype(str)
            .apply(lambda x: x.str.contains(buscar, case=False))
            .any(axis=1)
        ]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

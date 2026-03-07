from __future__ import annotations

import streamlit as st

from database.connection import db_transaction


def render_auditoria() -> None:
    st.subheader("Auditoría")
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT fecha, usuario, accion, valor_anterior, valor_nuevo
            FROM auditoria
            ORDER BY id DESC
            LIMIT 500
            """
        ).fetchall()
    st.dataframe(rows, use_container_width=True)


from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.audit_service import ensure_audit_log_table


def _load_audit_log(limit: int = 500) -> pd.DataFrame:
    ensure_audit_log_table()
    with db_transaction() as conn:
        return pd.read_sql_query(
            """
            SELECT id, fecha, usuario, modulo, accion, entidad, entidad_id, detalle, metadata
            FROM audit_log
            ORDER BY id DESC
            LIMIT ?
            """,
            conn,
            params=(int(limit),),
        )


def render_auditoria_operativa(usuario: str = "Sistema") -> None:
    st.subheader("🧾 Bitácora operativa")
    st.caption("Registro de acciones críticas: tickets, cierres, cambios de estado, aprobaciones y operaciones sensibles.")
    df = _load_audit_log()

    if df.empty:
        st.info("Todavía no hay eventos de auditoría registrados.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Eventos", len(df))
    c2.metric("Usuarios", df["usuario"].nunique())
    c3.metric("Módulos", df["modulo"].nunique())
    c4.metric("Acciones", df["accion"].nunique())

    col1, col2, col3 = st.columns(3)
    usuario_filter = col1.selectbox("Usuario", ["Todos"] + sorted(df["usuario"].dropna().astype(str).unique().tolist()))
    modulo_filter = col2.selectbox("Módulo", ["Todos"] + sorted(df["modulo"].dropna().astype(str).unique().tolist()))
    accion_filter = col3.selectbox("Acción", ["Todos"] + sorted(df["accion"].dropna().astype(str).unique().tolist()))

    vista = df.copy()
    if usuario_filter != "Todos":
        vista = vista[vista["usuario"].astype(str).eq(usuario_filter)]
    if modulo_filter != "Todos":
        vista = vista[vista["modulo"].astype(str).eq(modulo_filter)]
    if accion_filter != "Todos":
        vista = vista[vista["accion"].astype(str).eq(accion_filter)]

    st.dataframe(vista, use_container_width=True, hide_index=True)

    with st.expander("Resumen por módulo y acción"):
        resumen = df.groupby(["modulo", "accion"], as_index=False).agg(eventos=("id", "count"))
        st.dataframe(resumen.sort_values("eventos", ascending=False), use_container_width=True, hide_index=True)

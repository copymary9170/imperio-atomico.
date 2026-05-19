from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from services.audit_service import ensure_audit_log_table


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _download_csv(label: str, df: pd.DataFrame, filename_prefix: str) -> None:
    if df.empty:
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    st.download_button(
        label=f"⬇️ Descargar CSV · {label}",
        data=_csv_bytes(df),
        file_name=f"{filename_prefix}_{stamp}.csv",
        mime="text/csv",
        use_container_width=True,
    )


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

    col1, col2, col3, col4 = st.columns(4)
    usuario_filter = col1.selectbox("Usuario", ["Todos"] + sorted(df["usuario"].dropna().astype(str).unique().tolist()))
    modulo_filter = col2.selectbox("Módulo", ["Todos"] + sorted(df["modulo"].dropna().astype(str).unique().tolist()))
    accion_filter = col3.selectbox("Acción", ["Todos"] + sorted(df["accion"].dropna().astype(str).unique().tolist()))
    limite_visual = col4.number_input("Eventos a mostrar", min_value=25, max_value=500, value=200, step=25)

    vista = df.copy()
    if usuario_filter != "Todos":
        vista = vista[vista["usuario"].astype(str).eq(usuario_filter)]
    if modulo_filter != "Todos":
        vista = vista[vista["modulo"].astype(str).eq(modulo_filter)]
    if accion_filter != "Todos":
        vista = vista[vista["accion"].astype(str).eq(accion_filter)]

    vista = vista.head(int(limite_visual))
    st.dataframe(vista, use_container_width=True, hide_index=True)
    _download_csv("bitácora filtrada", vista, "bitacora_operativa_filtrada")

    with st.expander("Resumen por módulo y acción"):
        resumen = df.groupby(["modulo", "accion"], as_index=False).agg(eventos=("id", "count"))
        resumen = resumen.sort_values("eventos", ascending=False)
        st.dataframe(resumen, use_container_width=True, hide_index=True)
        _download_csv("resumen auditoría", resumen, "resumen_auditoria_modulo_accion")

    with st.expander("Eventos críticos sugeridos"):
        patrones = ["cierre", "eliminar", "actualizar", "aprobar", "emitir_comprobante"]
        mask = vista["accion"].astype(str).str.contains("|".join(patrones), case=False, na=False)
        criticos = vista[mask]
        if criticos.empty:
            st.info("No hay eventos críticos en la vista filtrada.")
        else:
            st.dataframe(criticos, use_container_width=True, hide_index=True)
            _download_csv("eventos críticos", criticos, "eventos_criticos_auditoria")

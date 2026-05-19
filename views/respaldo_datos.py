from __future__ import annotations

from datetime import datetime
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from security.permissions import has_permission, require_any_permission
from services.audit_service import log_audit_event

CRITICAL_TABLES = [
    "ventas",
    "clientes",
    "inventario",
    "movimientos_tesoreria",
    "cierres_caja",
    "cierres_caja_turnos",
    "comprobantes_pos",
    "comprobantes_pos_items",
    "cola_impresion",
    "contadores_impresion",
    "fichas_tecnicas_bom",
    "fichas_tecnicas_bom_componentes",
    "disenos_aprobaciones",
    "disenos_aprobaciones_eventos",
    "despachos_entregas",
    "despachos_eventos",
    "unidades_fraccionadas",
    "proveedores",
    "ordenes_compra",
    "audit_log",
    "migration_errors",
]


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _list_tables() -> list[str]:
    with db_transaction() as conn:
        rows = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()
    return [str(row[0]) for row in rows]


def _table_row_count(table_name: str) -> int:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table_name):
                return 0
            row = conn.execute(f"SELECT COUNT(*) AS total FROM {table_name}").fetchone()
        return int(row["total"] if row and "total" in row.keys() else (row[0] if row else 0))
    except Exception:
        return 0


def _table_columns(table_name: str) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table_name):
                return pd.DataFrame()
            rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        data = []
        for row in rows:
            data.append(
                {
                    "tabla": table_name,
                    "columna": row[1],
                    "tipo": row[2],
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "pk": bool(row[5]),
                }
            )
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def _data_dictionary(tables: list[str]) -> pd.DataFrame:
    frames = [_table_columns(table) for table in tables]
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame(columns=["tabla", "columna", "tipo", "not_null", "default", "pk"])
    return pd.concat(frames, ignore_index=True)


def _read_table(table_name: str, limit: int | None = None) -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, table_name):
            return pd.DataFrame()
        sql = f"SELECT * FROM {table_name}"
        if limit and limit > 0:
            sql += f" LIMIT {int(limit)}"
        return pd.read_sql_query(sql, conn)


def _csv_bytes(df: pd.DataFrame) -> bytes:
    return df.to_csv(index=False).encode("utf-8-sig")


def _zip_tables(tables: list[str], limit: int | None = None, include_dictionary: bool = True) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        manifest_rows = []
        for table in tables:
            df = _read_table(table, limit=limit)
            if df.empty and _table_row_count(table) == 0:
                csv_data = pd.DataFrame().to_csv(index=False).encode("utf-8-sig")
            else:
                csv_data = _csv_bytes(df)
            zf.writestr(f"tablas/{table}.csv", csv_data)
            manifest_rows.append({"tabla": table, "filas_exportadas": len(df), "filas_totales": _table_row_count(table)})
        manifest = pd.DataFrame(manifest_rows)
        zf.writestr("manifest.csv", _csv_bytes(manifest))
        if include_dictionary:
            diccionario = _data_dictionary(tables)
            zf.writestr("diccionario_datos.csv", _csv_bytes(diccionario))
    return buffer.getvalue()


def render_respaldo_datos(usuario: str = "Sistema") -> None:
    if not require_any_permission(["reportes.export", "config.view", "dashboard.view"], "🚫 No tienes acceso a respaldo/exportación de datos."):
        return

    puede_exportar = has_permission("reportes.export") or has_permission("config.view")

    st.title("🧰 Respaldo / Exportación de datos")
    st.caption("Descarga tablas críticas del ERP como CSV individual o ZIP general. Útil antes de cambios grandes o auditorías.")

    if not puede_exportar:
        st.warning("Modo consulta: necesitas permiso reportes.export para descargar respaldos.")

    tables = _list_tables()
    if not tables:
        st.info("No hay tablas disponibles para exportar.")
        return

    resumen = pd.DataFrame([
        {"tabla": table, "filas": _table_row_count(table), "critica": "Sí" if table in CRITICAL_TABLES else "No"}
        for table in tables
    ])

    c1, c2, c3 = st.columns(3)
    c1.metric("Tablas", len(tables))
    c2.metric("Tablas críticas", int(resumen["critica"].eq("Sí").sum()))
    c3.metric("Filas totales", int(resumen["filas"].sum()))

    tab_resumen, tab_zip, tab_individual, tab_diccionario = st.tabs([
        "Resumen",
        "ZIP general",
        "CSV individual",
        "Diccionario de datos",
    ])

    with tab_resumen:
        resumen_vista = resumen.sort_values(["critica", "filas"], ascending=[False, False])
        st.dataframe(resumen_vista, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar resumen CSV",
            data=_csv_bytes(resumen_vista),
            file_name=f"resumen_tablas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not puede_exportar,
        )

    with tab_zip:
        modo = st.radio("Qué respaldar", ["Tablas críticas", "Todas las tablas", "Seleccionar tablas"], horizontal=True, disabled=not puede_exportar)
        if modo == "Tablas críticas":
            selected = [t for t in CRITICAL_TABLES if t in tables]
        elif modo == "Todas las tablas":
            selected = tables
        else:
            selected = st.multiselect("Tablas", tables, default=[t for t in CRITICAL_TABLES if t in tables], disabled=not puede_exportar)

        limitar = st.checkbox("Limitar filas por tabla", value=False, disabled=not puede_exportar)
        limite = st.number_input("Límite de filas", min_value=100, max_value=100000, value=5000, step=100, disabled=not puede_exportar or not limitar)
        incluir_diccionario = st.checkbox("Incluir diccionario de datos", value=True, disabled=not puede_exportar)

        selected_key = "|".join(selected)
        backup_signature = f"{modo}|{selected_key}|{limitar}|{int(limite)}|{incluir_diccionario}"
        if st.session_state.get("backup_signature") != backup_signature:
            st.session_state.pop("backup_zip_data", None)
            st.session_state.pop("backup_zip_name", None)
            st.session_state["backup_signature"] = backup_signature

        if selected:
            if st.button("Preparar respaldo ZIP", type="primary", use_container_width=True, disabled=not puede_exportar):
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.session_state["backup_zip_data"] = _zip_tables(selected, limit=int(limite) if limitar else None, include_dictionary=incluir_diccionario)
                st.session_state["backup_zip_name"] = f"respaldo_erp_{stamp}.zip"
                log_audit_event(
                    usuario=usuario,
                    modulo="Sistema",
                    accion="preparar_respaldo_zip",
                    entidad="database",
                    entidad_id=stamp,
                    detalle=f"Respaldo ZIP preparado con {len(selected)} tabla(s).",
                    metadata={"tablas": selected, "limitado": limitar, "limite": int(limite) if limitar else None, "diccionario": incluir_diccionario},
                )
                st.success("Respaldo preparado. Ya puedes descargarlo abajo.")

            if st.session_state.get("backup_zip_data"):
                st.download_button(
                    "⬇️ Descargar respaldo ZIP preparado",
                    data=st.session_state["backup_zip_data"],
                    file_name=st.session_state.get("backup_zip_name", "respaldo_erp.zip"),
                    mime="application/zip",
                    use_container_width=True,
                    disabled=not puede_exportar,
                )
        else:
            st.info("Selecciona al menos una tabla.")

    with tab_individual:
        selected_table = st.selectbox("Tabla", tables, disabled=not puede_exportar)
        preview_limit = st.number_input("Filas de vista previa", min_value=10, max_value=1000, value=100, step=10)
        df_preview = _read_table(selected_table, limit=int(preview_limit))
        st.dataframe(df_preview, use_container_width=True, hide_index=True)
        full_df = _read_table(selected_table)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button(
            "⬇️ Descargar CSV de tabla",
            data=_csv_bytes(full_df),
            file_name=f"{selected_table}_{stamp}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not puede_exportar,
        )

    with tab_diccionario:
        diccionario = _data_dictionary(tables)
        st.dataframe(diccionario, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Descargar diccionario CSV",
            data=_csv_bytes(diccionario),
            file_name=f"diccionario_datos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            disabled=not puede_exportar,
        )

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


def _zip_tables(tables: list[str], limit: int | None = None) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        manifest_rows = []
        for table in tables:
            df = _read_table(table, limit=limit)
            if df.empty and _table_row_count(table) == 0:
                csv_data = pd.DataFrame().to_csv(index=False).encode("utf-8-sig")
            else:
                csv_data = _csv_bytes(df)
            zf.writestr(f"{table}.csv", csv_data)
            manifest_rows.append({"tabla": table, "filas_exportadas": len(df), "filas_totales": _table_row_count(table)})
        manifest = pd.DataFrame(manifest_rows)
        zf.writestr("manifest.csv", _csv_bytes(manifest))
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
        {
            "tabla": table,
            "filas": _table_row_count(table),
            "critica": "Sí" if table in CRITICAL_TABLES else "No",
        }
        for table in tables
    ])

    c1, c2, c3 = st.columns(3)
    c1.metric("Tablas", len(tables))
    c2.metric("Tablas críticas", int(resumen["critica"].eq("Sí").sum()))
    c3.metric("Filas totales", int(resumen["filas"].sum()))

    tab_resumen, tab_zip, tab_individual = st.tabs([
        "Resumen",
        "ZIP general",
        "CSV individual",
    ])

    with tab_resumen:
        st.dataframe(resumen.sort_values(["critica", "filas"], ascending=[False, False]), use_container_width=True, hide_index=True)

    with tab_zip:
        modo = st.radio(
            "Qué respaldar",
            ["Tablas críticas", "Todas las tablas", "Seleccionar tablas"],
            horizontal=True,
            disabled=not puede_exportar,
        )
        if modo == "Tablas críticas":
            selected = [t for t in CRITICAL_TABLES if t in tables]
        elif modo == "Todas las tablas":
            selected = tables
        else:
            selected = st.multiselect("Tablas", tables, default=[t for t in CRITICAL_TABLES if t in tables], disabled=not puede_exportar)

        limitar = st.checkbox("Limitar filas por tabla", value=False, disabled=not puede_exportar)
        limite = st.number_input("Límite de filas", min_value=100, max_value=100000, value=5000, step=100, disabled=not puede_exportar or not limitar)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if selected:
            zip_data = _zip_tables(selected, limit=int(limite) if limitar else None)
            st.download_button(
                "⬇️ Descargar respaldo ZIP",
                data=zip_data,
                file_name=f"respaldo_erp_{stamp}.zip",
                mime="application/zip",
                use_container_width=True,
                disabled=not puede_exportar,
            )
            if puede_exportar:
                log_audit_event(
                    usuario=usuario,
                    modulo="Sistema",
                    accion="generar_respaldo_zip",
                    entidad="database",
                    entidad_id=stamp,
                    detalle=f"Respaldo ZIP preparado con {len(selected)} tabla(s).",
                    metadata={"tablas": selected, "limitado": limitar, "limite": int(limite) if limitar else None},
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

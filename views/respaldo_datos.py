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

EXPECTED_MIN_COLUMNS = {
    "ventas": ["id", "fecha", "total_usd"],
    "clientes": ["id"],
    "inventario": ["id"],
    "movimientos_tesoreria": ["fecha", "tipo", "monto_usd", "metodo_pago", "estado"],
    "cierres_caja_turnos": ["fecha_operativa", "turno", "cajero", "diferencia_total_usd", "estado"],
    "comprobantes_pos": ["fecha", "usuario", "cliente", "total_usd", "cuerpo"],
    "fichas_tecnicas_bom": ["codigo", "producto", "costo_total_usd", "precio_sugerido_usd"],
    "disenos_aprobaciones": ["cliente", "nombre_diseno", "estado", "bloqueo_produccion"],
    "despachos_entregas": ["cliente", "tipo_entrega", "estado"],
    "unidades_fraccionadas": ["material", "unidad_compra", "unidad_consumo", "factor_conversion"],
    "proveedores": ["nombre"],
    "ordenes_compra": ["proveedor", "estado", "total_usd"],
    "audit_log": ["fecha", "usuario", "modulo", "accion"],
    "migration_errors": ["fecha", "area", "error"],
}

PRIORITY_ORDER = {"Alta": 0, "Media": 1, "Baja": 2, "OK": 3}


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
        return pd.DataFrame(
            [
                {
                    "tabla": table_name,
                    "columna": row[1],
                    "tipo": row[2],
                    "not_null": bool(row[3]),
                    "default": row[4],
                    "pk": bool(row[5]),
                }
                for row in rows
            ]
        )
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


def _problem_priority(*, table: str, exists: bool, row_count: int, missing: list[str], migration_errors_count: int) -> str:
    if not exists and table in CRITICAL_TABLES:
        return "Alta"
    if table == "migration_errors" and migration_errors_count > 0:
        return "Alta"
    if missing and table in CRITICAL_TABLES:
        return "Alta"
    if exists and table in CRITICAL_TABLES and row_count == 0:
        return "Media"
    if missing:
        return "Media"
    if table == "audit_log" and row_count == 0:
        return "Baja"
    return "OK"


def _data_health_report(existing_tables: list[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    existing_set = set(existing_tables)
    all_tables = sorted(existing_set.union(CRITICAL_TABLES))
    migration_errors_count = _table_row_count("migration_errors") if "migration_errors" in existing_set else 0

    for table in all_tables:
        exists = table in existing_set
        row_count = _table_row_count(table) if exists else 0
        cols_df = _table_columns(table) if exists else pd.DataFrame()
        columns = set(cols_df["columna"].astype(str).tolist()) if not cols_df.empty and "columna" in cols_df.columns else set()
        expected = EXPECTED_MIN_COLUMNS.get(table, [])
        missing = [col for col in expected if col not in columns]
        problems: list[str] = []

        if not exists:
            problems.append("tabla faltante")
        if exists and table in CRITICAL_TABLES and row_count == 0:
            problems.append("tabla crítica sin registros")
        if missing:
            problems.append("columnas mínimas faltantes: " + ", ".join(missing))
        if table == "migration_errors" and row_count > 0:
            problems.append("hay errores de migración registrados")
        if table == "audit_log" and row_count == 0:
            problems.append("sin eventos de auditoría")

        prioridad = _problem_priority(table=table, exists=exists, row_count=row_count, missing=missing, migration_errors_count=migration_errors_count)
        estado = "OK" if prioridad == "OK" else ("Falta" if not exists else "Revisar")

        rows.append(
            {
                "prioridad": prioridad,
                "estado": estado,
                "tabla": table,
                "critica": "Sí" if table in CRITICAL_TABLES else "No",
                "existe": "Sí" if exists else "No",
                "filas": row_count,
                "columnas": len(columns),
                "problemas": "; ".join(problems),
                "accion_sugerida": _suggest_action(table, prioridad, problems),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["prioridad_orden"] = df["prioridad"].map(PRIORITY_ORDER).fillna(9)
    return df.sort_values(["prioridad_orden", "critica", "filas"], ascending=[True, False, True]).drop(columns=["prioridad_orden"])


def _suggest_action(table: str, priority: str, problems: list[str]) -> str:
    if priority == "OK":
        return "Sin acción requerida."
    if "tabla faltante" in problems:
        return "Ejecutar diagnóstico técnico y revisar migraciones/esquema inicial."
    if any("columnas mínimas" in p for p in problems):
        return "Reiniciar app para correr migraciones y revisar database/auto_migrations.py."
    if table == "migration_errors":
        return "Abrir Diagnóstico técnico y revisar el detalle de migration_errors."
    if table == "audit_log":
        return "Usar módulos auditados para generar eventos o revisar permisos de auditoría."
    if "tabla crítica sin registros" in problems:
        return "Validar si es normal por arranque nuevo o cargar datos operativos iniciales."
    return "Revisar la tabla y completar datos faltantes."


def _zip_tables(tables: list[str], limit: int | None = None, include_dictionary: bool = True, include_health: bool = True) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, mode="w", compression=ZIP_DEFLATED) as zf:
        manifest_rows = []
        for table in tables:
            df = _read_table(table, limit=limit)
            csv_data = _csv_bytes(df) if not (df.empty and _table_row_count(table) == 0) else pd.DataFrame().to_csv(index=False).encode("utf-8-sig")
            zf.writestr(f"tablas/{table}.csv", csv_data)
            manifest_rows.append({"tabla": table, "filas_exportadas": len(df), "filas_totales": _table_row_count(table)})
        zf.writestr("manifest.csv", _csv_bytes(pd.DataFrame(manifest_rows)))
        if include_dictionary:
            zf.writestr("diccionario_datos.csv", _csv_bytes(_data_dictionary(tables)))
        if include_health:
            zf.writestr("salud_datos.csv", _csv_bytes(_data_health_report(_list_tables())))
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
    salud = _data_health_report(tables)
    problemas = salud[~salud["estado"].eq("OK")]
    alta = int(salud["prioridad"].eq("Alta").sum()) if not salud.empty else 0
    media = int(salud["prioridad"].eq("Media").sum()) if not salud.empty else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Tablas", len(tables))
    c2.metric("Tablas críticas", int(resumen["critica"].eq("Sí").sum()))
    c3.metric("Filas totales", int(resumen["filas"].sum()))
    c4.metric("Problemas", len(problemas), delta=f"Alta: {alta} · Media: {media}")

    tab_resumen, tab_salud, tab_zip, tab_individual, tab_diccionario = st.tabs([
        "Resumen",
        "Salud de datos",
        "ZIP general",
        "CSV individual",
        "Diccionario de datos",
    ])

    with tab_resumen:
        resumen_vista = resumen.sort_values(["critica", "filas"], ascending=[False, False])
        st.dataframe(resumen_vista, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar resumen CSV", data=_csv_bytes(resumen_vista), file_name=f"resumen_tablas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True, disabled=not puede_exportar)

    with tab_salud:
        if problemas.empty:
            st.success("Salud de datos sin problemas detectados en tablas críticas y estructura mínima.")
        else:
            st.warning(f"Hay {len(problemas)} tabla(s) con elementos para revisar. Prioridad alta: {alta}.")

        prioridad_filter = st.selectbox("Filtrar prioridad", ["Todas", "Alta", "Media", "Baja", "OK"])
        salud_vista = salud if prioridad_filter == "Todas" else salud[salud["prioridad"].eq(prioridad_filter)]
        st.dataframe(salud_vista, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar salud de datos CSV", data=_csv_bytes(salud), file_name=f"salud_datos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True, disabled=not puede_exportar)

        with st.expander("Matriz de criticidad"):
            matriz = salud.groupby(["prioridad", "critica"], as_index=False).agg(tablas=("tabla", "count"), filas=("filas", "sum"))
            matriz["prioridad_orden"] = matriz["prioridad"].map(PRIORITY_ORDER).fillna(9)
            matriz = matriz.sort_values(["prioridad_orden", "critica"], ascending=[True, False]).drop(columns=["prioridad_orden"])
            st.dataframe(matriz, use_container_width=True, hide_index=True)
            st.download_button("⬇️ Descargar matriz CSV", data=_csv_bytes(matriz), file_name=f"matriz_criticidad_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True, disabled=not puede_exportar)

        with st.expander("Solo problemas"):
            if problemas.empty:
                st.success("No hay problemas detectados.")
            else:
                st.dataframe(problemas, use_container_width=True, hide_index=True)
                st.download_button("⬇️ Descargar problemas CSV", data=_csv_bytes(problemas), file_name=f"problemas_salud_datos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True, disabled=not puede_exportar)

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
        incluir_salud = st.checkbox("Incluir salud de datos", value=True, disabled=not puede_exportar)

        selected_key = "|".join(selected)
        backup_signature = f"{modo}|{selected_key}|{limitar}|{int(limite)}|{incluir_diccionario}|{incluir_salud}"
        if st.session_state.get("backup_signature") != backup_signature:
            st.session_state.pop("backup_zip_data", None)
            st.session_state.pop("backup_zip_name", None)
            st.session_state["backup_signature"] = backup_signature

        if selected:
            if st.button("Preparar respaldo ZIP", type="primary", use_container_width=True, disabled=not puede_exportar):
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.session_state["backup_zip_data"] = _zip_tables(selected, limit=int(limite) if limitar else None, include_dictionary=incluir_diccionario, include_health=incluir_salud)
                st.session_state["backup_zip_name"] = f"respaldo_erp_{stamp}.zip"
                log_audit_event(usuario=usuario, modulo="Sistema", accion="preparar_respaldo_zip", entidad="database", entidad_id=stamp, detalle=f"Respaldo ZIP preparado con {len(selected)} tabla(s).", metadata={"tablas": selected, "limitado": limitar, "limite": int(limite) if limitar else None, "diccionario": incluir_diccionario, "salud_datos": incluir_salud})
                st.success("Respaldo preparado. Ya puedes descargarlo abajo.")

            if st.session_state.get("backup_zip_data"):
                st.download_button("⬇️ Descargar respaldo ZIP preparado", data=st.session_state["backup_zip_data"], file_name=st.session_state.get("backup_zip_name", "respaldo_erp.zip"), mime="application/zip", use_container_width=True, disabled=not puede_exportar)
        else:
            st.info("Selecciona al menos una tabla.")

    with tab_individual:
        selected_table = st.selectbox("Tabla", tables, disabled=not puede_exportar)
        preview_limit = st.number_input("Filas de vista previa", min_value=10, max_value=1000, value=100, step=10)
        df_preview = _read_table(selected_table, limit=int(preview_limit))
        st.dataframe(df_preview, use_container_width=True, hide_index=True)
        full_df = _read_table(selected_table)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        st.download_button("⬇️ Descargar CSV de tabla", data=_csv_bytes(full_df), file_name=f"{selected_table}_{stamp}.csv", mime="text/csv", use_container_width=True, disabled=not puede_exportar)

    with tab_diccionario:
        diccionario = _data_dictionary(tables)
        st.dataframe(diccionario, use_container_width=True, hide_index=True)
        st.download_button("⬇️ Descargar diccionario CSV", data=_csv_bytes(diccionario), file_name=f"diccionario_datos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", mime="text/csv", use_container_width=True, disabled=not puede_exportar)

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st

from database.connection import db_transaction


ALERTA_CONFIG = {
    "critica": "🔴 Crítica",
    "media": "🟠 Media",
    "info": "🔵 Info",
}


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


def _table_exists(conn, table_name: str) -> bool:
    try:
        return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None
    except Exception:
        return False


def _table_columns(conn, table_name: str) -> set[str]:
    try:
        if not _table_exists(conn, table_name):
            return set()
        return {str(r[1]) for r in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}
    except Exception:
        return set()


def _where_columns_available(existing: set[str], where_columns: list[str] | None) -> bool:
    return all(col in existing for col in (where_columns or []))


def _safe_count(table: str, where: str | None = None, where_columns: list[str] | None = None) -> int:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0
            existing = _table_columns(conn, table)
            if not _where_columns_available(existing, where_columns):
                return 0
            sql = f"SELECT COUNT(*) AS total FROM {table}"
            if where:
                sql += f" WHERE {where}"
            row = conn.execute(sql).fetchone()
        return int(row["total"] if row and "total" in row.keys() else (row[0] if row else 0))
    except Exception:
        return 0


def _safe_sum(table: str, column: str, where: str | None = None, where_columns: list[str] | None = None) -> float:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return 0.0
            existing = _table_columns(conn, table)
            if column not in existing or not _where_columns_available(existing, where_columns):
                return 0.0
            sql = f"SELECT SUM({column}) AS total FROM {table}"
            if where:
                sql += f" WHERE {where}"
            row = conn.execute(sql).fetchone()
        return float(row["total"] or 0) if row else 0.0
    except Exception:
        return 0.0


def _safe_df(table: str, columns: list[str], where: str | None = None, where_columns: list[str] | None = None, limit: int = 100) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table):
                return pd.DataFrame()
            existing = _table_columns(conn, table)
            if not _where_columns_available(existing, where_columns):
                return pd.DataFrame()
            selected = [c for c in columns if c in existing]
            if not selected:
                return pd.DataFrame()
            sql = f"SELECT {', '.join(selected)} FROM {table}"
            if where:
                sql += f" WHERE {where}"
            order_col = "id" if "id" in existing else selected[0]
            sql += f" ORDER BY {order_col} DESC LIMIT {int(limit)}"
            return pd.read_sql_query(sql, conn)
    except Exception:
        return pd.DataFrame()


def _ensure_migration_review_columns() -> None:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "migration_errors"):
                return
            existing = _table_columns(conn, "migration_errors")
            if "revisado" not in existing:
                conn.execute("ALTER TABLE migration_errors ADD COLUMN revisado INTEGER DEFAULT 0")
            if "fecha_revision" not in existing:
                conn.execute("ALTER TABLE migration_errors ADD COLUMN fecha_revision TEXT")
            if "usuario_revision" not in existing:
                conn.execute("ALTER TABLE migration_errors ADD COLUMN usuario_revision TEXT")
    except Exception:
        pass


def _migration_errors_count() -> int:
    _ensure_migration_review_columns()
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, "migration_errors"):
                return 0
            existing = _table_columns(conn, "migration_errors")
            where = "WHERE COALESCE(revisado, 0)=0" if "revisado" in existing else ""
            row = conn.execute(f"SELECT COUNT(*) AS total FROM migration_errors {where}").fetchone()
            return int(row["total"] if row else 0)
    except Exception:
        return _safe_count("migration_errors")


def _mark_migration_errors_reviewed(usuario: str) -> None:
    _ensure_migration_review_columns()
    with db_transaction() as conn:
        if not _table_exists(conn, "migration_errors"):
            return
        conn.execute(
            """
            UPDATE migration_errors
            SET revisado=1, fecha_revision=CURRENT_TIMESTAMP, usuario_revision=?
            WHERE COALESCE(revisado, 0)=0
            """,
            (usuario,),
        )


def _build_alerts() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    disenos_bloqueados = _safe_count("disenos_aprobaciones", "bloqueo_produccion=1", ["bloqueo_produccion"])
    if disenos_bloqueados:
        rows.append({"nivel": "critica", "modulo": "Diseños", "alerta": "Diseños bloqueando producción", "cantidad": disenos_bloqueados, "accion": "Revisar aprobación del cliente y cambiar estado a aprobado/listo."})

    despachos_abiertos = _safe_count("despachos_entregas", "estado NOT IN ('Entregado', 'Devuelto')", ["estado"])
    if despachos_abiertos:
        rows.append({"nivel": "media", "modulo": "Despacho", "alerta": "Despachos abiertos", "cantidad": despachos_abiertos, "accion": "Actualizar estados: por empaquetar, listo, en ruta o entregado."})

    cierres_diferencia = _safe_count("cierres_caja_turnos", "estado='Con diferencia'", ["estado"])
    diferencia_total = _safe_sum("cierres_caja_turnos", "diferencia_total_usd", "estado='Con diferencia'", ["estado"])
    if cierres_diferencia:
        rows.append({"nivel": "critica", "modulo": "Caja", "alerta": f"Cierres con diferencia (${diferencia_total:,.2f})", "cantidad": cierres_diferencia, "accion": "Revisar efectivo contado, métodos declarados y observaciones del cajero."})

    migration_errors = _migration_errors_count()
    if migration_errors:
        rows.append({"nivel": "media", "modulo": "Sistema", "alerta": "Errores de migración pendientes de revisión", "cantidad": migration_errors, "accion": "Abrir la pestaña Sistema, revisar detalle y marcar como revisado si no afecta operación."})

    cola_pendiente = _safe_count("cola_impresion", "estado NOT IN ('Completado', 'Cancelado', 'Entregado')", ["estado"])
    if cola_pendiente:
        rows.append({"nivel": "media", "modulo": "Cola impresión", "alerta": "Trabajos pendientes en cola", "cantidad": cola_pendiente, "accion": "Procesar archivos por prioridad y verificar especificaciones de impresión."})

    contadores_abiertos = _safe_count("contadores_impresion", "estado NOT IN ('Cuadrado', 'Cerrado')", ["estado"])
    if contadores_abiertos:
        rows.append({"nivel": "media", "modulo": "Contadores", "alerta": "Registros de contadores pendientes", "cantidad": contadores_abiertos, "accion": "Cuadrar contador inicial/final contra copias cobradas."})

    bom_borrador = _safe_count("fichas_tecnicas_bom", "estado IN ('Borrador', 'En revisión')", ["estado"])
    if bom_borrador:
        rows.append({"nivel": "info", "modulo": "BOM", "alerta": "Fichas técnicas no activas", "cantidad": bom_borrador, "accion": "Completar componentes, costos y activar recetas listas."})

    compras_pendientes = _safe_count("ordenes_compra", "estado NOT IN ('Recibida', 'Cerrada', 'Cancelada')", ["estado"])
    if compras_pendientes:
        rows.append({"nivel": "media", "modulo": "Compras", "alerta": "Órdenes de compra pendientes", "cantidad": compras_pendientes, "accion": "Revisar proveedor, recepción de mercancía y cuentas por pagar."})

    proveedores_incompletos = _safe_count("proveedores", "COALESCE(rif, '')='' OR COALESCE(telefono, '')=''", ["rif", "telefono"])
    if proveedores_incompletos:
        rows.append({"nivel": "info", "modulo": "Proveedores", "alerta": "Proveedores con ficha incompleta", "cantidad": proveedores_incompletos, "accion": "Completar RIF, teléfono, datos bancarios y condiciones de crédito."})

    if not rows:
        rows.append({"nivel": "info", "modulo": "ERP", "alerta": "Sin alertas críticas detectadas", "cantidad": 0, "accion": "Operación estable según las tablas revisadas."})

    df = pd.DataFrame(rows)
    df["nivel_label"] = df["nivel"].map(ALERTA_CONFIG).fillna(df["nivel"])
    return df


def render_centro_alertas(usuario: str = "Sistema") -> None:
    st.subheader("🚨 Centro de alertas operativas")
    st.caption("Resumen de bloqueos, pendientes y riesgos operativos que requieren atención.")

    alerts = _build_alerts()
    criticas = int(alerts["nivel"].eq("critica").sum())
    medias = int(alerts["nivel"].eq("media").sum())
    infos = int(alerts["nivel"].eq("info").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas", len(alerts))
    c2.metric("Críticas", criticas)
    c3.metric("Medias", medias)
    c4.metric("Informativas", infos)

    if criticas:
        st.error("Hay alertas críticas que pueden afectar caja, producción o estabilidad técnica.")
    elif medias:
        st.warning("Hay alertas operativas pendientes de seguimiento.")
    else:
        st.success("No hay alertas críticas detectadas.")

    alert_view = alerts[["nivel_label", "modulo", "alerta", "cantidad", "accion"]]
    st.dataframe(alert_view, use_container_width=True, hide_index=True)
    _download_csv("alertas", alert_view, "alertas_operativas")

    tab_disenos, tab_despacho, tab_caja, tab_sistema, tab_compras, tab_auditoria = st.tabs([
        "Diseños bloqueados",
        "Despachos abiertos",
        "Diferencias caja",
        "Sistema",
        "Compras / Proveedores",
        "Auditoría reciente",
    ])

    with tab_disenos:
        df = _safe_df("disenos_aprobaciones", ["id", "fecha_creacion", "cliente", "nombre_diseno", "estado", "bloqueo_produccion", "aprobado_por"], "bloqueo_produccion=1", ["bloqueo_produccion"])
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            _download_csv("diseños bloqueados", df, "disenos_bloqueados")
        else:
            st.success("No hay diseños bloqueando producción.")

    with tab_despacho:
        df = _safe_df("despachos_entregas", ["id", "fecha_creacion", "cliente", "tipo_entrega", "estado", "agencia_envio", "numero_guia", "costo_envio_usd"], "estado NOT IN ('Entregado', 'Devuelto')", ["estado"])
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            _download_csv("despachos abiertos", df, "despachos_abiertos")
        else:
            st.success("No hay despachos abiertos.")

    with tab_caja:
        df = _safe_df("cierres_caja_turnos", ["id", "fecha_operativa", "turno", "cajero", "efectivo_esperado_usd", "efectivo_contado_usd", "diferencia_efectivo_usd", "diferencia_total_usd", "estado", "observaciones"], "estado='Con diferencia'", ["estado"])
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            _download_csv("diferencias caja", df, "diferencias_caja")
        else:
            st.success("No hay cierres con diferencia.")

    with tab_sistema:
        _ensure_migration_review_columns()
        df = _safe_df("migration_errors", ["id", "fecha", "area", "tabla", "columna", "operacion", "error", "revisado", "fecha_revision", "usuario_revision"], None, None, 300)
        if not df.empty:
            pendientes = df[df.get("revisado", 0).fillna(0).astype(int).eq(0)] if "revisado" in df.columns else df
            revisados = df[df.get("revisado", 0).fillna(0).astype(int).eq(1)] if "revisado" in df.columns else pd.DataFrame()
            p1, p2 = st.columns(2)
            p1.metric("Pendientes de revisión", len(pendientes))
            p2.metric("Revisados / archivados", len(revisados))

            if not pendientes.empty:
                st.warning("Hay errores de migración pendientes. Revisa si afectan la operación antes de archivarlos.")
                st.dataframe(pendientes, use_container_width=True, hide_index=True)
                _download_csv("errores sistema pendientes", pendientes, "errores_migracion_pendientes")
                if st.button("Marcar errores pendientes como revisados", type="primary", use_container_width=True):
                    _mark_migration_errors_reviewed(usuario)
                    st.success("Errores de migración marcados como revisados.")
                    st.rerun()
            else:
                st.success("No hay errores de migración pendientes de revisión.")

            with st.expander("Ver errores revisados / archivados", expanded=False):
                if revisados.empty:
                    st.info("No hay errores archivados todavía.")
                else:
                    st.dataframe(revisados, use_container_width=True, hide_index=True)
                    _download_csv("errores sistema revisados", revisados, "errores_migracion_revisados")
        else:
            st.success("No hay errores de migración registrados.")

    with tab_compras:
        ordenes = _safe_df("ordenes_compra", ["id", "fecha", "proveedor", "estado", "total_usd", "observaciones"], "estado NOT IN ('Recibida', 'Cerrada', 'Cancelada')", ["estado"], 150)
        proveedores = _safe_df("proveedores", ["id", "nombre", "rif", "telefono", "email", "dias_credito", "banco", "cuenta"], "COALESCE(rif, '')='' OR COALESCE(telefono, '')=''", ["rif", "telefono"], 150)
        st.markdown("#### Órdenes pendientes")
        if not ordenes.empty:
            st.dataframe(ordenes, use_container_width=True, hide_index=True)
            _download_csv("órdenes pendientes", ordenes, "ordenes_compra_pendientes")
        else:
            st.success("No hay órdenes de compra pendientes.")
        st.markdown("#### Proveedores incompletos")
        if not proveedores.empty:
            st.dataframe(proveedores, use_container_width=True, hide_index=True)
            _download_csv("proveedores incompletos", proveedores, "proveedores_incompletos")
        else:
            st.success("No hay proveedores incompletos detectados.")

    with tab_auditoria:
        df = _safe_df("audit_log", ["id", "fecha", "usuario", "modulo", "accion", "entidad", "entidad_id", "detalle"], None, None, 200)
        if not df.empty:
            st.dataframe(df, use_container_width=True, hide_index=True)
            _download_csv("auditoría reciente", df, "auditoria_reciente")
        else:
            st.info("No hay auditoría registrada todavía.")

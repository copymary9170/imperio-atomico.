from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction


ALERTA_CONFIG = {
    "critica": "🔴 Crítica",
    "media": "🟠 Media",
    "info": "🔵 Info",
}


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _safe_count(table: str, where: str | None = None) -> int:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return 0
        sql = f"SELECT COUNT(*) AS total FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = conn.execute(sql).fetchone()
    return int(row["total"] if row and "total" in row.keys() else (row[0] if row else 0))


def _safe_sum(table: str, column: str, where: str | None = None) -> float:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return 0.0
        cols = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            return 0.0
        sql = f"SELECT SUM({column}) AS total FROM {table}"
        if where:
            sql += f" WHERE {where}"
        row = conn.execute(sql).fetchone()
    return float(row["total"] or 0) if row else 0.0


def _safe_df(table: str, columns: list[str], where: str | None = None, limit: int = 100) -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, table):
            return pd.DataFrame()
        existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        selected = [c for c in columns if c in existing]
        if not selected:
            return pd.DataFrame()
        sql = f"SELECT {', '.join(selected)} FROM {table}"
        if where:
            sql += f" WHERE {where}"
        sql += f" ORDER BY id DESC LIMIT {int(limit)}"
        return pd.read_sql_query(sql, conn)


def _build_alerts() -> pd.DataFrame:
    rows: list[dict[str, object]] = []

    disenos_bloqueados = _safe_count("disenos_aprobaciones", "bloqueo_produccion=1")
    if disenos_bloqueados:
        rows.append({"nivel": "critica", "modulo": "Diseños", "alerta": "Diseños bloqueando producción", "cantidad": disenos_bloqueados, "accion": "Revisar aprobación del cliente y cambiar estado a aprobado/listo."})

    despachos_abiertos = _safe_count("despachos_entregas", "estado NOT IN ('Entregado', 'Devuelto')")
    if despachos_abiertos:
        rows.append({"nivel": "media", "modulo": "Despacho", "alerta": "Despachos abiertos", "cantidad": despachos_abiertos, "accion": "Actualizar estados: por empaquetar, listo, en ruta o entregado."})

    cierres_diferencia = _safe_count("cierres_caja_turnos", "estado='Con diferencia'")
    diferencia_total = _safe_sum("cierres_caja_turnos", "diferencia_total_usd", "estado='Con diferencia'")
    if cierres_diferencia:
        rows.append({"nivel": "critica", "modulo": "Caja", "alerta": f"Cierres con diferencia (${diferencia_total:,.2f})", "cantidad": cierres_diferencia, "accion": "Revisar efectivo contado, métodos declarados y observaciones del cajero."})

    migration_errors = _safe_count("migration_errors")
    if migration_errors:
        rows.append({"nivel": "critica", "modulo": "Sistema", "alerta": "Errores de migración registrados", "cantidad": migration_errors, "accion": "Abrir Diagnóstico técnico y revisar la tabla migration_errors."})

    cola_pendiente = _safe_count("cola_impresion", "estado NOT IN ('Completado', 'Cancelado', 'Entregado')")
    if cola_pendiente:
        rows.append({"nivel": "media", "modulo": "Cola impresión", "alerta": "Trabajos pendientes en cola", "cantidad": cola_pendiente, "accion": "Procesar archivos por prioridad y verificar especificaciones de impresión."})

    contadores_abiertos = _safe_count("contadores_impresion", "estado NOT IN ('Cuadrado', 'Cerrado')")
    if contadores_abiertos:
        rows.append({"nivel": "media", "modulo": "Contadores", "alerta": "Registros de contadores pendientes", "cantidad": contadores_abiertos, "accion": "Cuadrar contador inicial/final contra copias cobradas."})

    bom_borrador = _safe_count("fichas_tecnicas_bom", "estado IN ('Borrador', 'En revisión')")
    if bom_borrador:
        rows.append({"nivel": "info", "modulo": "BOM", "alerta": "Fichas técnicas no activas", "cantidad": bom_borrador, "accion": "Completar componentes, costos y activar recetas listas."})

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

    st.dataframe(
        alerts[["nivel_label", "modulo", "alerta", "cantidad", "accion"]],
        use_container_width=True,
        hide_index=True,
    )

    tab_disenos, tab_despacho, tab_caja, tab_sistema = st.tabs([
        "Diseños bloqueados",
        "Despachos abiertos",
        "Diferencias caja",
        "Sistema",
    ])

    with tab_disenos:
        df = _safe_df("disenos_aprobaciones", ["id", "fecha_creacion", "cliente", "nombre_diseno", "estado", "bloqueo_produccion", "aprobado_por"], "bloqueo_produccion=1")
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("No hay diseños bloqueando producción.")

    with tab_despacho:
        df = _safe_df("despachos_entregas", ["id", "fecha_creacion", "cliente", "tipo_entrega", "estado", "agencia_envio", "numero_guia", "costo_envio_usd"], "estado NOT IN ('Entregado', 'Devuelto')")
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("No hay despachos abiertos.")

    with tab_caja:
        df = _safe_df("cierres_caja_turnos", ["id", "fecha_operativa", "turno", "cajero", "efectivo_esperado_usd", "efectivo_contado_usd", "diferencia_efectivo_usd", "diferencia_total_usd", "estado", "observaciones"], "estado='Con diferencia'")
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("No hay cierres con diferencia.")

    with tab_sistema:
        df = _safe_df("migration_errors", ["id", "fecha", "area", "tabla", "columna", "operacion", "error"], None, 200)
        st.dataframe(df, use_container_width=True, hide_index=True) if not df.empty else st.success("No hay errores de migración registrados.")

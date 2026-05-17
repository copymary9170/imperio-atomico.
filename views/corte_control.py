from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from database.connection import db_transaction


def _table_exists(conn: Any, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _load_ordenes() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "ordenes_corte"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT id, codigo, fecha, referencia, material_nombre, equipo_nombre,
                   ruta_codigo, orden_produccion_id, prioridad, estado,
                   area_cm2_estimada, cm_corte_estimado, tiempo_estimado_min,
                   costo_material_estimado_usd, costo_mano_obra_estimado_usd,
                   costo_desgaste_estimado_usd, costo_total_estimado_usd,
                   cantidad_material_estimada, lote
            FROM ordenes_corte
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )


def _load_ejecuciones() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "ejecuciones_corte") or not _table_exists(conn, "ordenes_corte"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT e.id, e.orden_corte_id, o.codigo, o.referencia, o.material_nombre,
                   o.equipo_nombre, o.ruta_codigo, e.fecha_inicio, e.fecha_fin, e.usuario,
                   e.cm_corte_real, e.tiempo_real_min, e.material_real_usado,
                   e.merma, e.retazo_reutilizable,
                   e.costo_material_real_usd, e.costo_mano_obra_real_usd,
                   e.costo_desgaste_real_usd, e.costo_real_usd,
                   e.desgaste_registrado, e.incidencias, e.estado_final,
                   o.cm_corte_estimado, o.tiempo_estimado_min, o.costo_total_estimado_usd,
                   o.cantidad_material_estimada
            FROM ejecuciones_corte e
            JOIN ordenes_corte o ON o.id = e.orden_corte_id
            ORDER BY e.id DESC
            """,
            conn,
        )


def _load_retazos() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "retazos_corte") or not _table_exists(conn, "ordenes_corte"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT r.id, r.orden_corte_id, o.codigo, o.referencia, r.material_nombre,
                   r.cantidad, r.unidad, r.reutilizable, r.observaciones, r.fecha
            FROM retazos_corte r
            JOIN ordenes_corte o ON o.id = r.orden_corte_id
            ORDER BY r.fecha DESC, r.id DESC
            """,
            conn,
        )


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def _prepare_ejecuciones(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    for col in [
        "cm_corte_real", "tiempo_real_min", "material_real_usado", "merma",
        "retazo_reutilizable", "costo_real_usd", "costo_material_real_usd",
        "costo_mano_obra_real_usd", "costo_desgaste_real_usd",
        "desgaste_registrado", "cm_corte_estimado", "tiempo_estimado_min",
        "costo_total_estimado_usd", "cantidad_material_estimada",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["eficiencia_material_pct"] = out.apply(
        lambda r: 0.0 if float(r.get("material_real_usado", 0) or 0) <= 0 else max(0.0, min(100.0, ((float(r.get("material_real_usado", 0)) - float(r.get("merma", 0))) / float(r.get("material_real_usado", 0))) * 100)),
        axis=1,
    )
    out["retazo_pct"] = out.apply(
        lambda r: 0.0 if float(r.get("material_real_usado", 0) or 0) <= 0 else max(0.0, min(100.0, (float(r.get("retazo_reutilizable", 0)) / float(r.get("material_real_usado", 0))) * 100)),
        axis=1,
    )
    out["desviacion_tiempo_min"] = out["tiempo_real_min"] - out["tiempo_estimado_min"]
    out["desviacion_costo_usd"] = out["costo_real_usd"] - out["costo_total_estimado_usd"]
    out["desviacion_cm"] = out["cm_corte_real"] - out["cm_corte_estimado"]
    return out


def render_corte_control(usuario: str = "Sistema") -> None:
    st.subheader("📊 Control de corte industrial")
    st.caption("Eficiencia, merma, retazos, costos reales vs estimados, tiempos y desempeño por equipo.")

    ordenes = _load_ordenes()
    ejec = _prepare_ejecuciones(_load_ejecuciones())
    retazos = _load_retazos()

    if ordenes.empty:
        st.info("Todavía no hay órdenes de corte registradas.")
        return

    ordenes_abiertas = ordenes[ordenes["estado"].astype(str).isin(["analizado", "aprobado", "en_proceso"])] if "estado" in ordenes.columns else pd.DataFrame()
    total_estimado = float(_num(ordenes, "costo_total_estimado_usd").sum())
    total_real = float(_num(ejec, "costo_real_usd").sum()) if not ejec.empty else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Órdenes", len(ordenes))
    c2.metric("Órdenes abiertas", len(ordenes_abiertas))
    c3.metric("Ejecuciones", len(ejec) if not ejec.empty else 0)
    c4.metric("Costo real", f"${total_real:,.2f}", f"${total_real - total_estimado:,.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("Cm reales", f"{float(_num(ejec, 'cm_corte_real').sum()):,.2f}" if not ejec.empty else "0.00")
    c6.metric("Merma", f"{float(_num(ejec, 'merma').sum()):,.2f}" if not ejec.empty else "0.00")
    c7.metric("Retazo reutilizable", f"{float(_num(ejec, 'retazo_reutilizable').sum()):,.2f}" if not ejec.empty else "0.00")
    eficiencia = float(ejec["eficiencia_material_pct"].mean()) if not ejec.empty and "eficiencia_material_pct" in ejec.columns else 0.0
    c8.metric("Eficiencia material", f"{eficiencia:,.1f}%")

    st.divider()

    tab_ordenes, tab_ejec, tab_retazos, tab_costos, tab_reco = st.tabs([
        "Órdenes",
        "Ejecuciones",
        "Retazos y merma",
        "Costos y tiempos",
        "Recomendaciones",
    ])

    with tab_ordenes:
        f1, f2, f3 = st.columns(3)
        estado = f1.selectbox("Estado", ["Todos"] + sorted(ordenes["estado"].fillna("Sin estado").astype(str).unique().tolist()))
        prioridad = f2.selectbox("Prioridad", ["Todas"] + sorted(ordenes["prioridad"].fillna("Sin prioridad").astype(str).unique().tolist()))
        equipo = f3.selectbox("Equipo", ["Todos"] + sorted(ordenes["equipo_nombre"].fillna("Sin equipo").astype(str).unique().tolist()))
        vista = ordenes.copy()
        if estado != "Todos":
            vista = vista[vista["estado"].fillna("Sin estado").astype(str).eq(estado)]
        if prioridad != "Todas":
            vista = vista[vista["prioridad"].fillna("Sin prioridad").astype(str).eq(prioridad)]
        if equipo != "Todos":
            vista = vista[vista["equipo_nombre"].fillna("Sin equipo").astype(str).eq(equipo)]
        st.dataframe(vista, use_container_width=True, hide_index=True)

    with tab_ejec:
        if ejec.empty:
            st.info("No hay ejecuciones registradas todavía.")
        else:
            st.dataframe(ejec, use_container_width=True, hide_index=True)
            if "equipo_nombre" in ejec.columns:
                resumen = ejec.groupby("equipo_nombre", as_index=False).agg(
                    ejecuciones=("id", "count"),
                    cm_reales=("cm_corte_real", "sum"),
                    tiempo_real=("tiempo_real_min", "sum"),
                    costo_real=("costo_real_usd", "sum"),
                    eficiencia=("eficiencia_material_pct", "mean"),
                ).sort_values("costo_real", ascending=False)
                st.markdown("#### Desempeño por equipo")
                st.dataframe(resumen, use_container_width=True, hide_index=True)

    with tab_retazos:
        if ejec.empty and retazos.empty:
            st.info("Sin retazos o mermas registradas.")
        else:
            if not ejec.empty:
                merma_equipo = ejec.groupby("equipo_nombre", as_index=False).agg(
                    merma=("merma", "sum"),
                    retazo=("retazo_reutilizable", "sum"),
                    material_usado=("material_real_usado", "sum"),
                ).sort_values("merma", ascending=False)
                st.dataframe(merma_equipo, use_container_width=True, hide_index=True)
                st.bar_chart(merma_equipo.set_index("equipo_nombre")["merma"])
            if not retazos.empty:
                st.markdown("#### Detalle de retazos")
                st.dataframe(retazos, use_container_width=True, hide_index=True)

    with tab_costos:
        if ejec.empty:
            st.info("No hay costos reales para comparar.")
        else:
            cols = [
                "codigo", "referencia", "material_nombre", "equipo_nombre",
                "cm_corte_estimado", "cm_corte_real", "desviacion_cm",
                "tiempo_estimado_min", "tiempo_real_min", "desviacion_tiempo_min",
                "costo_total_estimado_usd", "costo_real_usd", "desviacion_costo_usd",
                "eficiencia_material_pct", "estado_final",
            ]
            st.dataframe(ejec[[c for c in cols if c in ejec.columns]].sort_values("desviacion_costo_usd", ascending=False), use_container_width=True, hide_index=True)
            chart = ejec[["codigo", "costo_total_estimado_usd", "costo_real_usd"]].copy()
            chart = chart.set_index("codigo")
            st.bar_chart(chart)

    with tab_reco:
        recomendaciones = []
        if len(ordenes_abiertas) > 0:
            recomendaciones.append(f"Hay {len(ordenes_abiertas)} orden(es) abiertas; priorizar aprobación, ejecución o cierre.")
        if not ejec.empty and float(ejec["merma"].sum()) > 0:
            recomendaciones.append("Revisar patrones de merma por equipo y material para ajustar presión, velocidad y profundidad.")
        if not ejec.empty and float(ejec["desviacion_costo_usd"].sum()) > 0:
            recomendaciones.append("Actualizar costos estándar: el costo real está superando el estimado.")
        if not ejec.empty and float(ejec["desviacion_tiempo_min"].sum()) > 0:
            recomendaciones.append("Revisar tiempos de preparación/corte; el tiempo real está por encima del estimado.")
        if not ejec.empty and eficiencia < 85:
            recomendaciones.append("La eficiencia material está baja; revisar anidado, aprovechamiento y recuperación de retazos.")
        recomendaciones.append("Usar retazos reutilizables como inventario separado para reducir costo de materiales.")
        recomendaciones.append("Relacionar órdenes de corte con rutas de producción para comparar estándar vs real.")
        recomendaciones.append("Registrar desgaste por equipo para anticipar mantenimiento de cuchillas y plotters.")
        for reco in recomendaciones:
            st.write(f"- {reco}")

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


def _load_lotes() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "sublimacion_lotes"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT id, codigo, fecha, cliente, producto, tipo_producto, maquina,
                   cantidad_programada, cantidad_producida, cantidad_aprobada,
                   cantidad_reproceso, cantidad_merma, cantidad_rechazada,
                   consumo_tinta_estimado_ml, consumo_tinta_real_ml,
                   consumo_material_estimado_unid, consumo_material_real_unid,
                   tiempo_total_estimado_min, tiempo_total_real_min,
                   costo_total_final, costo_total_real,
                   merma_pct, calidad_acabado, estado
            FROM sublimacion_lotes
            ORDER BY fecha DESC, id DESC
            """,
            conn,
        )


def _load_calidad() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "sublimacion_control_calidad") or not _table_exists(conn, "sublimacion_lotes"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT qc.fecha, qc.lote_id, l.codigo, l.producto, l.cliente,
                   qc.color_correcto, qc.transferencia_completa, qc.sin_manchas,
                   qc.sin_ghosting, qc.sin_quemado, qc.resultado, qc.observaciones
            FROM sublimacion_control_calidad qc
            JOIN sublimacion_lotes l ON l.id = qc.lote_id
            ORDER BY qc.fecha DESC, qc.id DESC
            """,
            conn,
        )


def _load_mermas() -> pd.DataFrame:
    with db_transaction() as conn:
        if not _table_exists(conn, "sublimacion_mermas") or not _table_exists(conn, "sublimacion_lotes"):
            return pd.DataFrame()
        return pd.read_sql_query(
            """
            SELECT m.fecha, m.lote_id, l.codigo, l.producto, l.cliente,
                   m.tipo_falla, m.cantidad, m.costo_estimado_usd, m.observaciones
            FROM sublimacion_mermas m
            JOIN sublimacion_lotes l ON l.id = m.lote_id
            ORDER BY m.fecha DESC, m.id DESC
            """,
            conn,
        )


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    if df.empty or col not in df.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


def _prepare_lotes(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    out["fecha"] = pd.to_datetime(out["fecha"], errors="coerce")
    for col in [
        "cantidad_programada", "cantidad_producida", "cantidad_aprobada",
        "cantidad_reproceso", "cantidad_merma", "cantidad_rechazada",
        "consumo_tinta_estimado_ml", "consumo_tinta_real_ml",
        "consumo_material_estimado_unid", "consumo_material_real_unid",
        "tiempo_total_estimado_min", "tiempo_total_real_min",
        "costo_total_final", "costo_total_real", "merma_pct",
    ]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    out["desviacion_costo_usd"] = out["costo_total_real"] - out["costo_total_final"]
    out["desviacion_tiempo_min"] = out["tiempo_total_real_min"] - out["tiempo_total_estimado_min"]
    out["rendimiento_aprobacion_pct"] = out.apply(
        lambda r: 0.0 if float(r.get("cantidad_producida", 0) or 0) <= 0 else (float(r.get("cantidad_aprobada", 0) or 0) / float(r.get("cantidad_producida", 0))) * 100,
        axis=1,
    )
    return out


def render_sublimacion_control(usuario: str = "Sistema") -> None:
    st.subheader("📊 Control de sublimación")
    st.caption("Productividad, calidad, mermas, costos reales vs estimados y recomendaciones operativas.")

    lotes = _prepare_lotes(_load_lotes())
    calidad = _load_calidad()
    mermas = _load_mermas()

    if lotes.empty:
        st.info("Todavía no hay lotes de sublimación registrados.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lotes", len(lotes))
    c2.metric("Producido", f"{float(lotes['cantidad_producida'].sum()):,.2f}")
    c3.metric("Aprobado", f"{float(lotes['cantidad_aprobada'].sum()):,.2f}")
    c4.metric("Merma", f"{float(lotes['cantidad_merma'].sum()):,.2f}")

    c5, c6, c7, c8 = st.columns(4)
    costo_estimado = float(lotes["costo_total_final"].sum())
    costo_real = float(lotes["costo_total_real"].sum())
    tiempo_estimado = float(lotes["tiempo_total_estimado_min"].sum())
    tiempo_real = float(lotes["tiempo_total_real_min"].sum())
    c5.metric("Costo real", f"${costo_real:,.2f}", f"${costo_real - costo_estimado:,.2f}")
    c6.metric("Costo estimado", f"${costo_estimado:,.2f}")
    c7.metric("Tiempo real", f"{tiempo_real:,.1f} min", f"{tiempo_real - tiempo_estimado:,.1f} min")
    aprobacion = (float(lotes["cantidad_aprobada"].sum()) / float(lotes["cantidad_producida"].sum()) * 100) if float(lotes["cantidad_producida"].sum()) > 0 else 0.0
    c8.metric("Aprobación", f"{aprobacion:,.1f}%")

    st.divider()

    tab_lotes, tab_calidad, tab_mermas, tab_costos, tab_reco = st.tabs([
        "Lotes",
        "Calidad",
        "Mermas",
        "Costos y tiempos",
        "Recomendaciones",
    ])

    with tab_lotes:
        filtros = st.columns(3)
        estado = filtros[0].selectbox("Estado", ["Todos"] + sorted(lotes["estado"].dropna().astype(str).unique().tolist()))
        maquina = filtros[1].selectbox("Máquina", ["Todas"] + sorted(lotes["maquina"].fillna("Sin máquina").astype(str).unique().tolist()))
        tipo = filtros[2].selectbox("Tipo producto", ["Todos"] + sorted(lotes["tipo_producto"].fillna("Otro").astype(str).unique().tolist()))
        vista = lotes.copy()
        if estado != "Todos":
            vista = vista[vista["estado"].astype(str).eq(estado)]
        if maquina != "Todas":
            vista = vista[vista["maquina"].fillna("Sin máquina").astype(str).eq(maquina)]
        if tipo != "Todos":
            vista = vista[vista["tipo_producto"].fillna("Otro").astype(str).eq(tipo)]
        st.dataframe(vista, use_container_width=True, hide_index=True)

    with tab_calidad:
        if calidad.empty:
            st.info("No hay registros de control de calidad.")
        else:
            resumen = calidad.groupby("resultado", as_index=False).agg(revisiones=("lote_id", "count"))
            st.dataframe(resumen, use_container_width=True, hide_index=True)
            st.bar_chart(resumen.set_index("resultado")["revisiones"])
            st.dataframe(calidad, use_container_width=True, hide_index=True)

    with tab_mermas:
        if mermas.empty:
            st.success("No hay mermas registradas.")
        else:
            resumen_merma = mermas.groupby("tipo_falla", as_index=False).agg(
                cantidad=("cantidad", "sum"),
                costo=("costo_estimado_usd", "sum"),
                eventos=("lote_id", "count"),
            ).sort_values("costo", ascending=False)
            st.dataframe(resumen_merma, use_container_width=True, hide_index=True)
            st.bar_chart(resumen_merma.set_index("tipo_falla")["costo"])
            st.dataframe(mermas, use_container_width=True, hide_index=True)

    with tab_costos:
        cols = [
            "codigo", "producto", "maquina", "cantidad_producida",
            "costo_total_final", "costo_total_real", "desviacion_costo_usd",
            "tiempo_total_estimado_min", "tiempo_total_real_min", "desviacion_tiempo_min",
            "rendimiento_aprobacion_pct", "estado",
        ]
        st.dataframe(lotes[[c for c in cols if c in lotes.columns]].sort_values("desviacion_costo_usd", ascending=False), use_container_width=True, hide_index=True)
        if "fecha" in lotes.columns:
            trend = lotes.dropna(subset=["fecha"]).sort_values("fecha")
            if not trend.empty:
                st.line_chart(trend.set_index("fecha")[["costo_total_final", "costo_total_real"]])

    with tab_reco:
        recomendaciones = []
        if float(lotes["cantidad_merma"].sum()) > 0:
            recomendaciones.append("Revisar causas de merma y crear checklist por tipo de producto antes de transferir.")
        if costo_real > costo_estimado:
            recomendaciones.append("Actualizar costos estándar: el costo real está por encima del estimado.")
        if tiempo_real > tiempo_estimado:
            recomendaciones.append("Revisar tiempos de preparación, impresión y transferencia; hay desviación de tiempo.")
        if aprobacion < 90 and float(lotes["cantidad_producida"].sum()) > 0:
            recomendaciones.append("La aprobación está por debajo de 90%; reforzar control de temperatura, presión y tiempo.")
        pendientes = lotes[lotes["estado"].astype(str).isin(["pendiente", "analizado", "en_proceso"])]
        if not pendientes.empty:
            recomendaciones.append(f"Hay {len(pendientes)} lote(s) abiertos; priorizar cierre o actualización de estado.")
        recomendaciones.append("Comparar cada lote con rutas de producción para estandarizar tiempos y costos.")
        recomendaciones.append("Registrar consumo real de tinta y material para mejorar precio sugerido y rentabilidad.")
        for reco in recomendaciones:
            st.write(f"- {reco}")

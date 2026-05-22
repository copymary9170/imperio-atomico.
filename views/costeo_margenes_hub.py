from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from views.costeo import render_costeo
from views.fichas_tecnicas_bom import render_fichas_tecnicas_bom
from views.rentabilidad import render_rentabilidad
from views.erp_nuevos_modulos import render_costeo_industrial


def _table_exists(conn, table_name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)).fetchone() is not None


def _read_table(table_name: str, limit: int = 500) -> pd.DataFrame:
    try:
        with db_transaction() as conn:
            if not _table_exists(conn, table_name):
                return pd.DataFrame()
            return pd.read_sql_query(f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT {int(limit)}", conn)
    except Exception:
        return pd.DataFrame()


def _metric_sum(df: pd.DataFrame, column: str) -> float:
    if df.empty or column not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[column], errors="coerce").fillna(0.0).sum())


def _render_resumen_costos(usuario: str) -> None:
    st.subheader("📊 Resumen de costos y márgenes")
    st.caption("Vista ejecutiva de costeos, recetas/BOM, cierres reales, precios sugeridos y desviaciones.")

    costeos = _read_table("costeos", 1000)
    bom = _read_table("fichas_tecnicas_bom", 1000)
    componentes = _read_table("fichas_tecnicas_bom_componentes", 1000)

    costo_estimado = _metric_sum(costeos, "costo_total_usd")
    precio_sugerido = _metric_sum(costeos, "precio_sugerido_usd")
    costo_bom = _metric_sum(bom, "costo_total_usd")
    precio_bom = _metric_sum(bom, "precio_sugerido_usd")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Costeos guardados", len(costeos))
    c2.metric("Costo estimado", f"${costo_estimado:,.2f}")
    c3.metric("Precio sugerido", f"${precio_sugerido:,.2f}")
    c4.metric("Margen estimado", f"${precio_sugerido - costo_estimado:,.2f}")

    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Fichas BOM", len(bom))
    b2.metric("Componentes", len(componentes))
    b3.metric("Costo recetas", f"${costo_bom:,.2f}")
    b4.metric("Precio recetas", f"${precio_bom:,.2f}")

    if not costeos.empty:
        st.markdown("#### Últimos costeos")
        st.dataframe(costeos.head(15), use_container_width=True, hide_index=True)
    if not bom.empty:
        st.markdown("#### Últimas fichas / recetas")
        st.dataframe(bom.head(15), use_container_width=True, hide_index=True)


def _render_desviaciones(usuario: str) -> None:
    st.subheader("📉 Desviaciones estimado vs real")
    st.caption("Busca trabajos con costo real superior al estimado o margen real deteriorado.")
    costeos = _read_table("costeos", 1000)
    if costeos.empty:
        st.info("No hay costeos registrados todavía.")
        return

    df = costeos.copy()
    numeric_cols = [
        "costo_total_usd",
        "costo_real_usd",
        "precio_sugerido_usd",
        "precio_vendido_usd",
        "diferencia_vs_estimado_usd",
        "margen_real_pct",
    ]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

    if "diferencia_vs_estimado_usd" not in df.columns:
        if {"costo_total_usd", "costo_real_usd"}.issubset(df.columns):
            df["diferencia_vs_estimado_usd"] = df["costo_real_usd"] - df["costo_total_usd"]
        else:
            df["diferencia_vs_estimado_usd"] = 0.0

    desviadas = df[df["diferencia_vs_estimado_usd"].abs() > 0].copy()
    desviadas = desviadas.sort_values("diferencia_vs_estimado_usd", ascending=False)

    c1, c2, c3 = st.columns(3)
    c1.metric("Costeos con desviación", len(desviadas))
    c2.metric("Mayor sobrecosto", f"${float(desviadas['diferencia_vs_estimado_usd'].max()) if not desviadas.empty else 0:,.2f}")
    c3.metric("Desviación total", f"${float(desviadas['diferencia_vs_estimado_usd'].sum()) if not desviadas.empty else 0:,.2f}")

    if desviadas.empty:
        st.success("No hay desviaciones registradas con la información disponible.")
    else:
        st.dataframe(desviadas, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Exportar desviaciones CSV",
            data=desviadas.to_csv(index=False).encode("utf-8-sig"),
            file_name="desviaciones_costeo.csv",
            mime="text/csv",
            use_container_width=True,
        )


def _render_alertas_margen(usuario: str) -> None:
    st.subheader("🚨 Alertas de margen")
    st.caption("Detecta costeos sin cierre, márgenes negativos, BOM incompletas y desviaciones altas.")

    costeos = _read_table("costeos", 1000)
    bom = _read_table("fichas_tecnicas_bom", 1000)
    componentes = _read_table("fichas_tecnicas_bom_componentes", 2000)
    alertas: list[dict] = []
    datasets: dict[str, pd.DataFrame] = {}

    if not costeos.empty:
        df = costeos.copy()
        for col in ["costo_total_usd", "costo_real_usd", "precio_vendido_usd", "precio_sugerido_usd", "margen_real_pct", "diferencia_vs_estimado_usd"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)

        if "estado" in df.columns:
            sin_cerrar = df[~df["estado"].astype(str).str.lower().isin(["cerrado", "finalizado", "completado"])]
            datasets["Costeos sin cerrar"] = sin_cerrar
            if not sin_cerrar.empty:
                alertas.append({"nivel": "Media", "alerta": "Costeos sin cerrar", "cantidad": len(sin_cerrar), "acción": "Registrar costo real y cerrar el trabajo."})

        if {"precio_vendido_usd", "costo_real_usd"}.issubset(df.columns):
            precio_bajo = df[(df["precio_vendido_usd"] > 0) & (df["costo_real_usd"] > 0) & (df["precio_vendido_usd"] < df["costo_real_usd"])]
            datasets["Precio vendido menor al costo"] = precio_bajo
            if not precio_bajo.empty:
                alertas.append({"nivel": "Alta", "alerta": "Precio vendido menor al costo real", "cantidad": len(precio_bajo), "acción": "Revisar precio, descuentos y costos reales."})

        if "margen_real_pct" in df.columns:
            margen_negativo = df[df["margen_real_pct"] < 0]
            datasets["Margen negativo"] = margen_negativo
            if not margen_negativo.empty:
                alertas.append({"nivel": "Alta", "alerta": "Costeos con margen negativo", "cantidad": len(margen_negativo), "acción": "Corregir precio o estructura de costos."})

        if "diferencia_vs_estimado_usd" in df.columns:
            desviacion_alta = df[df["diferencia_vs_estimado_usd"].abs() >= 10]
            datasets["Desviación alta"] = desviacion_alta
            if not desviacion_alta.empty:
                alertas.append({"nivel": "Media", "alerta": "Desviación real vs estimado alta", "cantidad": len(desviacion_alta), "acción": "Revisar merma, materiales, horas y energía."})

    if not bom.empty:
        bom_df = bom.copy()
        comp_fichas = set(componentes["ficha_id"].astype(int)) if not componentes.empty and "ficha_id" in componentes.columns else set()
        if "id" in bom_df.columns:
            sin_componentes = bom_df[~bom_df["id"].astype(int).isin(comp_fichas)]
            datasets["BOM sin componentes"] = sin_componentes
            if not sin_componentes.empty:
                alertas.append({"nivel": "Alta", "alerta": "BOM sin componentes", "cantidad": len(sin_componentes), "acción": "Agregar materiales/mano de obra antes de cotizar."})
        if "estado" in bom_df.columns:
            obsoletas = bom_df[bom_df["estado"].astype(str).str.lower().isin(["obsoleta", "en revisión"])]
            datasets["BOM en revisión/obsoleta"] = obsoletas
            if not obsoletas.empty:
                alertas.append({"nivel": "Media", "alerta": "BOM en revisión u obsoleta", "cantidad": len(obsoletas), "acción": "Actualizar o activar receta vigente."})
        if "margen_sugerido_pct" in bom_df.columns:
            margen_cero = bom_df[pd.to_numeric(bom_df["margen_sugerido_pct"], errors="coerce").fillna(0) <= 0]
            datasets["BOM sin margen"] = margen_cero
            if not margen_cero.empty:
                alertas.append({"nivel": "Media", "alerta": "Fichas sin margen sugerido", "cantidad": len(margen_cero), "acción": "Definir margen antes de vender."})

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Alertas", len(alertas))
    c2.metric("Costeos", len(costeos))
    c3.metric("BOM", len(bom))
    c4.metric("Componentes", len(componentes))

    if alertas:
        st.dataframe(pd.DataFrame(alertas), use_container_width=True, hide_index=True)
    else:
        st.success("Sin alertas críticas de margen con la información disponible.")

    datasets = {k: v for k, v in datasets.items() if not v.empty}
    if datasets:
        tabs = st.tabs(list(datasets.keys()))
        for tab, (nombre, df) in zip(tabs, datasets.items()):
            with tab:
                st.dataframe(df, use_container_width=True, hide_index=True)


def render_costeo_margenes_hub(usuario: str = "Sistema") -> None:
    st.title("🧮 Costeo y Márgenes")
    st.caption("Hub de costos: costeo rápido, costeo industrial, BOM/recetas, rentabilidad por trabajo, desviaciones y alertas de margen.")

    secciones = {
        "📊 Resumen de costos": lambda: _render_resumen_costos(usuario),
        "🧮 Costeo rápido": lambda: render_costeo(usuario),
        "🏭 Costeo industrial": lambda: render_costeo_industrial(usuario),
        "📝 BOM / Recetas": lambda: render_fichas_tecnicas_bom(usuario),
        "📈 Rentabilidad por trabajo": lambda: render_rentabilidad(usuario),
        "📉 Desviaciones": lambda: _render_desviaciones(usuario),
        "🚨 Alertas de margen": lambda: _render_alertas_margen(usuario),
    }

    seccion = st.radio("Sección de costeo", list(secciones.keys()), horizontal=True, key="costeo_margenes_seccion_activa")
    st.divider()
    secciones[seccion]()

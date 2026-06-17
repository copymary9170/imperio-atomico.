from __future__ import annotations

import pandas as pd
import streamlit as st

from database.connection import db_transaction
from database.transactional_core import ensure_transactional_core_schema
from services.dashboard_metrics_service import calcular_metricas_ejecutivas, guardar_snapshot_metricas
from services.domain_events import fetch_pending_domain_events


def _read_table(table_name: str, limit: int = 100) -> pd.DataFrame:
    with db_transaction() as conn:
        return pd.read_sql_query(
            f"SELECT * FROM {table_name} ORDER BY id DESC LIMIT ?",
            conn,
            params=(int(limit),),
        )


def render_nucleo_transaccional(usuario: str = "Sistema") -> None:
    st.title("⚛️ Núcleo transaccional")
    st.caption("Eventos, reglas de negocio y métricas ejecutivas conectadas al ERP.")

    ensure_transactional_core_schema()

    periodo = st.radio("Periodo de métricas", ["diario", "mensual"], horizontal=True)
    metricas = calcular_metricas_ejecutivas(periodo=periodo)

    cols = st.columns(4)
    cols[0].metric("Ventas", f"$ {metricas['ventas_usd']:.2f}")
    cols[1].metric("Utilidad estimada", f"$ {metricas['utilidad_estimada_usd']:.2f}")
    cols[2].metric("Gastos", f"$ {metricas['gastos_usd']:.2f}")
    cols[3].metric("Alertas críticas", metricas["alertas_criticas"])

    cols = st.columns(4)
    cols[0].metric("CxC", f"$ {metricas['cuentas_por_cobrar_usd']:.2f}")
    cols[1].metric("CxP", f"$ {metricas['cuentas_por_pagar_usd']:.2f}")
    cols[2].metric("Stock crítico", metricas["stock_critico"])
    cols[3].metric("Trabajos pendientes", metricas["trabajos_pendientes"])

    if st.button("Guardar snapshot de métricas", use_container_width=True):
        snapshot_id = guardar_snapshot_metricas(periodo=periodo)
        st.success(f"Snapshot guardado: #{snapshot_id}")

    tab_eventos, tab_reglas, tab_snapshots = st.tabs(["Eventos", "Reglas", "Snapshots"])

    with tab_eventos:
        pendientes = fetch_pending_domain_events(limit=50)
        st.subheader("Eventos pendientes")
        if pendientes:
            st.dataframe(pd.DataFrame(pendientes), use_container_width=True, hide_index=True)
        else:
            st.info("No hay eventos pendientes.")
        st.subheader("Últimos eventos")
        st.dataframe(_read_table("eventos_transaccionales", 100), use_container_width=True, hide_index=True)

    with tab_reglas:
        st.dataframe(_read_table("reglas_negocio_transaccionales", 100), use_container_width=True, hide_index=True)

    with tab_snapshots:
        st.dataframe(_read_table("metricas_dashboard_snapshot", 100), use_container_width=True, hide_index=True)

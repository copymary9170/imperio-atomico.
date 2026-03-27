from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from services.operacion_industrial_service import OperacionIndustrialService


def render_operacion_industrial_dashboard(usuario: str, service: OperacionIndustrialService) -> None:
    st.title("🏭 Operación industrial unificada")
    st.caption(
        "Activos + diagnóstico técnico/visual + mantenimiento planificado en una sola experiencia operativa."
    )

    overview = service.get_executive_overview()
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Inversión instalada", f"${overview['inversion_instalada']:,.2f}")
    col2.metric("Activos", overview["total_activos"])
    col3.metric("Backlog mantenimiento", overview["backlog_abierto"])
    col4.metric("Equipos principales", overview["equipos_principales"])

    tabs = st.tabs(
        [
            "📦 Catálogo",
            "🧪 Diagnóstico",
            "🛠️ Mantenimiento",
            "🚨 Criticidad",
            "📜 Trazabilidad",
        ]
    )

    with tabs[0]:
        _render_catalogo(service)
    with tabs[1]:
        _render_diagnosticos(service)
    with tabs[2]:
        _render_mantenimiento(usuario, service)
    with tabs[3]:
        _render_criticidad(overview)
    with tabs[4]:
        _render_trazabilidad(service)


def _render_catalogo(service: OperacionIndustrialService) -> None:
    st.subheader("Catálogo unificado de activos")
    assets = service.list_assets()
    if not assets:
        st.info("No hay activos registrados todavía.")
        return
    df = pd.DataFrame(assets)
    st.dataframe(df, use_container_width=True, hide_index=True)


def _render_diagnosticos(service: OperacionIndustrialService) -> None:
    st.subheader("Diagnóstico técnico y visual")
    st.caption(
        "Cada lectura preserva método de estimación (software/OCR/visual/manual), fuente y nivel de confianza."
    )
    diagnostics = service.list_recent_diagnostics(limit=100)
    if not diagnostics:
        st.warning("Aún no existen diagnósticos técnicos registrados.")
        return
    st.dataframe(pd.DataFrame(diagnostics), use_container_width=True, hide_index=True)


def _render_mantenimiento(usuario: str, service: OperacionIndustrialService) -> None:
    st.subheader("Gestión de mantenimiento")
    activos = service.list_assets()
    activos_by_label = {
        f"#{item['id']} · {item.get('equipo', 'Activo')} ({item.get('unidad') or 'N/A'})": item["id"]
        for item in activos
    }

    with st.form("operacion_industrial_maintenance_form", clear_on_submit=True):
        activo_label = st.selectbox("Activo", options=list(activos_by_label.keys()) if activos_by_label else ["Sin activos"])
        tipo = st.selectbox("Tipo", ["preventivo", "correctivo"])
        estado = st.selectbox("Estado", ["pendiente", "programado", "en_ejecucion", "completado", "cancelado"])
        fecha_programada = st.date_input("Fecha programada")
        tecnico = st.text_input("Técnico / responsable")
        descripcion = st.text_area("Descripción de intervención")
        costo_estimado = st.number_input("Costo estimado (USD)", min_value=0.0, step=1.0)
        notas = st.text_area("Notas")
        evidencia = st.text_input("Evidencia URL o referencia")

        submitted = st.form_submit_button("Crear orden")
        if submitted:
            if not activos_by_label:
                st.error("No puedes crear órdenes sin activos registrados.")
                return
            try:
                order_id = service.create_maintenance_order(
                    activo_id=activos_by_label[activo_label],
                    tipo=tipo,
                    estado=estado,
                    fecha_programada=fecha_programada,
                    tecnico_responsable=tecnico,
                    descripcion=descripcion,
                    usuario=usuario,
                    costo_estimado=costo_estimado,
                    notas=notas,
                    evidencia_url=evidencia,
                )
                st.success(f"Orden de mantenimiento #{order_id} creada correctamente.")
            except Exception as exc:  # noqa: BLE001
                st.error(str(exc))

    backlog = service.list_maintenance_backlog()
    if backlog:
        st.markdown("#### Agenda / backlog priorizado")
        st.dataframe(pd.DataFrame(backlog), use_container_width=True, hide_index=True)
    else:
        st.info("Sin órdenes activas en backlog.")


def _render_criticidad(overview: dict[str, Any]) -> None:
    st.subheader("Motor de criticidad y priorización")
    critic = overview.get("activos_criticos") or []
    if not critic:
        st.info("No hay datos suficientes para priorizar todavía.")
        return
    st.dataframe(pd.DataFrame(critic), use_container_width=True, hide_index=True)


def _render_trazabilidad(service: OperacionIndustrialService) -> None:
    st.subheader("Trazabilidad y auditoría unificada")
    history = service.list_unified_history(limit=250)
    if not history:
        st.info("No hay eventos de trazabilidad para mostrar.")
        return
    st.dataframe(pd.DataFrame(history), use_container_width=True, hide_index=True)

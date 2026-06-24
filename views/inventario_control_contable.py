from __future__ import annotations

from datetime import date

import streamlit as st

from services.inventario_control_contable_service import (
    auditar_integridad,
    crear_cierre,
    detalle_cierre,
    listar_cierres,
)


def render_inventario_control_contable(usuario: str) -> None:
    st.subheader("🧮 Control contable del inventario")
    st.caption(
        "Verifica costos, existencias, lotes, facturas y movimientos antes de cerrar cada período."
    )

    tabs = st.tabs(["Auditoría de integridad", "Cierre mensual", "Historial de cierres"])

    with tabs[0]:
        hallazgos = auditar_integridad()
        if hallazgos.empty:
            st.success("No se detectaron inconsistencias contables o de inventario.")
        else:
            criticos = int((hallazgos["severidad"] == "CRÍTICA").sum())
            altos = int((hallazgos["severidad"] == "ALTA").sum())
            c1, c2, c3 = st.columns(3)
            c1.metric("Hallazgos", len(hallazgos))
            c2.metric("Críticos", criticos)
            c3.metric("Altos", altos)
            st.dataframe(hallazgos, use_container_width=True, hide_index=True)
            if criticos:
                st.error("Los hallazgos críticos deben resolverse antes de realizar el cierre mensual.")

    with tabs[1]:
        st.warning(
            "El cierre crea una fotografía inalterable de cantidades, costos y valor total. "
            "No modifica el stock."
        )
        hoy = date.today()
        periodo_default = f"{hoy.year:04d}-{hoy.month:02d}"
        with st.form("inventario_cierre_mensual"):
            periodo = st.text_input("Período", value=periodo_default, placeholder="AAAA-MM")
            observaciones = st.text_area("Observaciones", placeholder="Conteo validado, diferencias revisadas...")
            confirmar = st.checkbox("Confirmo que revisé la auditoría y el conteo físico")
            guardar = st.form_submit_button(
                "Crear cierre mensual",
                type="primary",
                use_container_width=True,
                disabled=not confirmar,
            )
        if guardar:
            try:
                cierre_id = crear_cierre(periodo, usuario, observaciones)
                st.success(f"Cierre #{cierre_id} creado para {periodo}.")
                st.rerun()
            except Exception as exc:
                st.error(str(exc))

    with tabs[2]:
        cierres = listar_cierres()
        if cierres.empty:
            st.info("Todavía no hay cierres mensuales registrados.")
        else:
            st.dataframe(cierres, use_container_width=True, hide_index=True)
            ids = [int(x) for x in cierres["id"].tolist()]
            etiquetas = {
                int(row["id"]): f"{row['periodo']} · ${float(row['valor_total_usd']):,.2f} · {row['usuario']}"
                for _, row in cierres.iterrows()
            }
            cierre_id = st.selectbox("Ver detalle", ids, format_func=lambda value: etiquetas[value])
            detalle = detalle_cierre(cierre_id)
            st.dataframe(detalle, use_container_width=True, hide_index=True)

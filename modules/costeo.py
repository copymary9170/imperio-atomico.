from __future__ import annotations

import pandas as pd
import streamlit as st

from services.costeo_service import (
    calcular_costo_servicio,
    calcular_margen_estimado,
    guardar_costeo,
    listar_costeos,
    obtener_parametros_costeo,
)

TIPOS_PROCESO = [
    "Servicio general",
    "Impresión",
    "Sublimación",
    "Corte",
    "Instalación",
]


def _df_desglose(costo_data: dict) -> pd.DataFrame:
    componentes = costo_data.get("componentes", {})
    return pd.DataFrame(
        [
            {"concepto": "Materiales", "subtotal_usd": float(componentes.get("materiales_usd", 0.0))},
            {"concepto": "Mano de obra", "subtotal_usd": float(componentes.get("mano_obra_usd", 0.0))},
            {"concepto": "Indirecto directo", "subtotal_usd": float(componentes.get("indirecto_directo_usd", 0.0))},
            {"concepto": "Imprevistos", "subtotal_usd": float(componentes.get("imprevistos_usd", 0.0))},
            {"concepto": "Indirecto factor", "subtotal_usd": float(componentes.get("indirecto_factor_usd", 0.0))},
        ]
    )


def render_costeo(usuario: str):
    st.subheader("🧮 Costeo básico (Fase 1)")

    parametros = obtener_parametros_costeo()

    with st.expander("⚙️ Parámetros base activos", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("Imprevistos", f"{float(parametros.get('factor_imprevistos_pct', 0)):.1f}%")
        c2.metric("Indirecto", f"{float(parametros.get('factor_indirecto_pct', 0)):.1f}%")
        c3.metric("Margen objetivo", f"{float(parametros.get('margen_objetivo_pct', 0)):.1f}%")

    with st.form("costeo_form"):
        tipo = st.selectbox("Tipo de proceso", TIPOS_PROCESO)
        descripcion = st.text_input("Descripción", placeholder="Ej: Banner 2x1 + instalación")

        c1, c2 = st.columns(2)
        with c1:
            cantidad = st.number_input("Cantidad", min_value=0.01, value=1.0, step=1.0)
            costo_materiales = st.number_input("Costo materiales (USD)", min_value=0.0, value=10.0, step=0.5)
        with c2:
            costo_mano_obra = st.number_input("Costo mano de obra (USD)", min_value=0.0, value=5.0, step=0.5)
            costo_indirecto = st.number_input("Costo indirecto directo (USD)", min_value=0.0, value=2.0, step=0.5)

        margen_pct = st.number_input(
            "Margen objetivo (%)",
            min_value=0.0,
            max_value=300.0,
            value=float(parametros.get("margen_objetivo_pct", 35.0)),
            step=1.0,
        )

        submitted = st.form_submit_button("Calcular costo + precio sugerido", use_container_width=True)

    if submitted:
        costo_data = calcular_costo_servicio(
            tipo_proceso=tipo,
            cantidad=float(cantidad),
            costo_materiales_usd=float(costo_materiales),
            costo_mano_obra_usd=float(costo_mano_obra),
            costo_indirecto_usd=float(costo_indirecto),
            parametros_override=parametros,
        )
        margen_data = calcular_margen_estimado(
            costo_total_usd=float(costo_data["costo_total_usd"]),
            margen_pct=float(margen_pct),
        )

        st.session_state["costeo_actual"] = {
            "tipo": tipo,
            "descripcion": descripcion,
            "cantidad": float(cantidad),
            "costo_materiales": float(costo_materiales),
            "costo_mano_obra": float(costo_mano_obra),
            "costo_indirecto": float(costo_indirecto),
            "margen_pct": float(margen_pct),
            "costo_data": costo_data,
            "margen_data": margen_data,
        }

    actual = st.session_state.get("costeo_actual")
    if not actual:
        st.info("Ingresa parámetros y ejecuta el cálculo para ver desglose, margen y precio sugerido.")
        return

    costo_data = actual["costo_data"]
    margen_data = actual["margen_data"]
    desglose_df = _df_desglose(costo_data)

    st.markdown("### Desglose del costo")
    st.dataframe(desglose_df, use_container_width=True, hide_index=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Costo total", f"$ {float(costo_data['costo_total_usd']):,.2f}")
    m2.metric("Costo unitario", f"$ {float(costo_data['costo_unitario_usd']):,.2f}")
    m3.metric("Margen estimado", f"{float(margen_data['margen_estimado_pct']):,.2f}%")
    m4.metric("Precio sugerido", f"$ {float(margen_data['precio_sugerido_usd']):,.2f}")

    if st.button("💾 Guardar cálculo", use_container_width=True):
        orden_id = guardar_costeo(
            usuario=usuario,
            tipo_proceso=str(actual["tipo"]),
            descripcion=str(actual.get("descripcion") or "Costeo rápido"),
            cantidad=float(actual["cantidad"]),
            costo_materiales_usd=float(actual["costo_materiales"]),
            costo_mano_obra_usd=float(actual["costo_mano_obra"]),
            costo_indirecto_usd=float(actual["costo_indirecto"]),
            margen_pct=float(actual["margen_pct"]),
            precio_sugerido_usd=float(margen_data["precio_sugerido_usd"]),
        )
        st.success(f"Costeo #{orden_id} guardado correctamente.")

    st.divider()
    st.caption("Últimos cálculos guardados")
    historial = listar_costeos(limit=20)
    if historial.empty:
        st.info("Aún no hay costeos guardados.")
    else:
        st.dataframe(historial, use_container_width=True, hide_index=True)

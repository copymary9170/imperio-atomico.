from __future__ import annotations

import pandas as pd
import streamlit as st

from services.costeo_service import (
    calcular_costo_servicio,
    calcular_margen_estimado,
    guardar_costeo,
    listar_costeos,
    obtener_parametros_costeo,
    registrar_costeo_real,
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
    st.subheader("🧮 Costeo unificado (Fase 1 + Fase 2)")

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
    st.subheader("🏁 Cierre de costeo real (Fase 2)")
    historial_cierre = listar_costeos(limit=100)
    if historial_cierre.empty:
        st.info("No hay costeos para cerrar.")
    else:
        opciones = {
            int(row["id"]): (
                f"#{int(row['id'])} · {row['descripcion']} · "
                f"Est: $ {float(row['costo_total_usd']):,.2f} · Estado: {row['estado']}"
            )
            for _, row in historial_cierre.iterrows()
        }
        orden_sel = st.selectbox(
            "Selecciona orden de costeo",
            options=list(opciones.keys()),
            format_func=lambda oid: opciones[oid],
            key="costeo_cierre_orden",
        )
        with st.form("form_cierre_costeo_real"):
            c1, c2, c3 = st.columns(3)
            materiales_real = c1.number_input("Materiales consumidos (USD)", min_value=0.0, value=0.0, step=0.5)
            merma_real = c2.number_input("Merma (USD)", min_value=0.0, value=0.0, step=0.5)
            mano_obra_real = c3.number_input("Mano de obra real (USD)", min_value=0.0, value=0.0, step=0.5)

            c4, c5, c6 = st.columns(3)
            tiempo_real = c4.number_input("Tiempo real (horas)", min_value=0.0, value=0.0, step=0.25)
            energia_real = c5.number_input("Energía / indirectos reales (USD)", min_value=0.0, value=0.0, step=0.5)
            ajustes_real = c6.number_input("Ajustes manuales (USD)", value=0.0, step=0.5)

            c7, c8, c9 = st.columns(3)
            precio_vendido = c7.number_input("Precio vendido (USD, opcional)", min_value=0.0, value=0.0, step=0.5)
            venta_id = c8.number_input("ID venta (opcional)", min_value=0, value=0, step=1)
            orden_prod_id = c9.number_input("ID orden producción (opcional)", min_value=0, value=0, step=1)
            cerrar_directo = st.checkbox("Cerrar costeo ahora", value=True)

            submit_cierre = st.form_submit_button("Registrar costo real", use_container_width=True)

        if submit_cierre:
            resultado = registrar_costeo_real(
                orden_id=int(orden_sel),
                usuario=usuario,
                materiales_consumidos_usd=float(materiales_real),
                merma_usd=float(merma_real),
                mano_obra_real_usd=float(mano_obra_real),
                tiempo_real_horas=float(tiempo_real),
                energia_indirectos_reales_usd=float(energia_real),
                ajustes_manual_usd=float(ajustes_real),
                precio_vendido_usd=float(precio_vendido) if float(precio_vendido) > 0 else None,
                venta_id=int(venta_id) if int(venta_id) > 0 else None,
                orden_produccion_id=int(orden_prod_id) if int(orden_prod_id) > 0 else None,
                cerrar=bool(cerrar_directo),
            )
            st.success(
                "Costeo real registrado. "
                f"Costo real: $ {resultado['costo_real_usd']:,.2f} · "
                f"Margen real: {resultado['margen_real_pct']:,.2f}% · "
                f"Δ vs estimado: $ {resultado['diferencia_vs_estimado_usd']:,.2f}"
            )
            st.rerun()

    st.divider()
    st.caption("Últimos cálculos guardados")
    historial = listar_costeos(limit=20)
    if historial.empty:
        st.info("Aún no hay costeos guardados.")
    else:
        st.dataframe(historial, use_container_width=True, hide_index=True)

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

PAPELES_COPY_MARY = {
    "Bond carta": {"costo_usd": 9.0 / 500, "nota": "Resma de 500 hojas a $9"},
    "Fotográfico mate": {"costo_usd": 5.0 / 20, "nota": "Paquete de 20 hojas a $5"},
    "Fotográfico brillante": {"costo_usd": 9.0 / 50, "nota": "Paquete de 50 hojas a $9"},
    "Opalina": {"costo_usd": 0.25, "nota": "Costo por hoja"},
    "Acetato": {"costo_usd": 1.50, "nota": "Costo por hoja"},
}

PERFILES_TINTA_COPY_MARY = {
    "Blanco y negro": {"tinta_usd_hoja": 19.0 / 12000, "minimo_usd_hoja": 0.25},
    "Color baja cobertura": {"tinta_usd_hoja": 0.012, "minimo_usd_hoja": 0.35},
    "Color media cobertura": {"tinta_usd_hoja": 0.028, "minimo_usd_hoja": 0.60},
    "Color alta cobertura": {"tinta_usd_hoja": 0.055, "minimo_usd_hoja": 1.00},
    "Foto / imagen completa": {"tinta_usd_hoja": 0.090, "minimo_usd_hoja": 1.50},
}


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


def _precio_con_margen(costo: float, margen_pct: float) -> float:
    margen = min(max(float(margen_pct), 0.0), 95.0)
    return round(float(costo) / (1 - margen / 100), 2) if costo > 0 else 0.0


def _render_calculadora_impresion_copy_mary(usuario: str, parametros: dict) -> None:
    st.subheader("🖨️ Calculadora de impresión Copy Mary")
    st.caption("Calcula precio mínimo y precio recomendado sin guardar archivos del cliente dentro del ERP.")

    with st.form("form_calculadora_impresion_copy_mary"):
        c1, c2, c3 = st.columns(3)
        tipo_impresion = c1.selectbox("Tipo de impresión", list(PERFILES_TINTA_COPY_MARY.keys()))
        papel = c2.selectbox("Papel", list(PAPELES_COPY_MARY.keys()))
        cantidad = c3.number_input("Cantidad de hojas", min_value=1, value=1, step=1)

        papel_data = PAPELES_COPY_MARY[papel]
        tinta_data = PERFILES_TINTA_COPY_MARY[tipo_impresion]

        c4, c5, c6 = st.columns(3)
        costo_papel_hoja = c4.number_input(
            "Costo papel por hoja (USD)",
            min_value=0.0,
            value=float(papel_data["costo_usd"]),
            step=0.01,
            format="%.4f",
            help=str(papel_data["nota"]),
        )
        costo_tinta_hoja = c5.number_input(
            "Costo tinta por hoja (USD)",
            min_value=0.0,
            value=float(tinta_data["tinta_usd_hoja"]),
            step=0.005,
            format="%.4f",
        )
        costo_cabezal_hoja = c6.number_input(
            "Desgaste cabezal por hoja (USD)",
            min_value=0.0,
            value=0.005,
            step=0.001,
            format="%.4f",
        )

        c7, c8, c9 = st.columns(3)
        mano_obra_hoja = c7.number_input(
            "Mano de obra por hoja (USD)",
            min_value=0.0,
            value=0.010,
            step=0.005,
            format="%.4f",
        )
        indirectos_hoja = c8.number_input(
            "Servicios/indirectos por hoja (USD)",
            min_value=0.0,
            value=0.005,
            step=0.005,
            format="%.4f",
        )
        merma_pct = c9.number_input("Merma (%)", min_value=0.0, max_value=100.0, value=3.0, step=1.0, format="%.2f")

        c10, c11 = st.columns(2)
        margen_pct = c10.number_input(
            "Margen objetivo (%)",
            min_value=0.0,
            max_value=95.0,
            value=float(parametros.get("margen_objetivo_pct", 35.0)),
            step=1.0,
            format="%.2f",
        )
        precio_zona_hoja = c11.number_input(
            "Precio zona / comparación por hoja (USD, opcional)",
            min_value=0.0,
            value=0.0,
            step=0.05,
            format="%.2f",
        )

        calcular = st.form_submit_button("Calcular impresión", use_container_width=True)

    if not calcular:
        return

    cantidad_val = int(cantidad)
    costo_base_hoja = float(costo_papel_hoja) + float(costo_tinta_hoja) + float(costo_cabezal_hoja) + float(mano_obra_hoja) + float(indirectos_hoja)
    costo_merma_hoja = costo_base_hoja * (float(merma_pct) / 100)
    costo_total_hoja = round(costo_base_hoja + costo_merma_hoja, 4)
    costo_total = round(costo_total_hoja * cantidad_val, 2)

    precio_minimo_hoja = max(costo_total_hoja, float(tinta_data.get("minimo_usd_hoja", 0.0)))
    precio_recomendado_hoja = max(_precio_con_margen(costo_total_hoja, float(margen_pct)), float(tinta_data.get("minimo_usd_hoja", 0.0)))
    precio_minimo_total = round(precio_minimo_hoja * cantidad_val, 2)
    precio_recomendado_total = round(precio_recomendado_hoja * cantidad_val, 2)
    utilidad_recomendada = round(precio_recomendado_total - costo_total, 2)
    margen_real = round((utilidad_recomendada / precio_recomendado_total) * 100, 2) if precio_recomendado_total else 0.0

    st.markdown("### Resultado")
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Costo por hoja", f"$ {costo_total_hoja:,.4f}")
    m2.metric("Costo total", f"$ {costo_total:,.2f}")
    m3.metric("Precio mínimo", f"$ {precio_minimo_total:,.2f}")
    m4.metric("Precio recomendado", f"$ {precio_recomendado_total:,.2f}")
    m5.metric("Margen", f"{margen_real:,.2f}%")

    desglose = pd.DataFrame(
        [
            {"concepto": "Papel", "usd_por_hoja": float(costo_papel_hoja), "total_usd": float(costo_papel_hoja) * cantidad_val},
            {"concepto": "Tinta", "usd_por_hoja": float(costo_tinta_hoja), "total_usd": float(costo_tinta_hoja) * cantidad_val},
            {"concepto": "Cabezal", "usd_por_hoja": float(costo_cabezal_hoja), "total_usd": float(costo_cabezal_hoja) * cantidad_val},
            {"concepto": "Mano de obra", "usd_por_hoja": float(mano_obra_hoja), "total_usd": float(mano_obra_hoja) * cantidad_val},
            {"concepto": "Indirectos", "usd_por_hoja": float(indirectos_hoja), "total_usd": float(indirectos_hoja) * cantidad_val},
            {"concepto": "Merma", "usd_por_hoja": float(costo_merma_hoja), "total_usd": float(costo_merma_hoja) * cantidad_val},
        ]
    )
    st.dataframe(
        desglose,
        use_container_width=True,
        hide_index=True,
        column_config={
            "usd_por_hoja": st.column_config.NumberColumn("USD por hoja", format="%.4f"),
            "total_usd": st.column_config.NumberColumn("Total USD", format="%.2f"),
        },
    )

    if precio_zona_hoja > 0:
        precio_zona_total = round(float(precio_zona_hoja) * cantidad_val, 2)
        utilidad_zona = round(precio_zona_total - costo_total, 2)
        if utilidad_zona < 0:
            st.error(f"Con el precio de zona pierdes $ {abs(utilidad_zona):,.2f} en este trabajo.")
        else:
            margen_zona = round((utilidad_zona / precio_zona_total) * 100, 2) if precio_zona_total else 0.0
            st.success(f"Con el precio de zona ganas $ {utilidad_zona:,.2f} · margen {margen_zona:,.2f}%")

    descripcion = f"{tipo_impresion} en {papel} · {cantidad_val} hoja(s)"
    if st.button("💾 Pasar este cálculo al historial de costeo", use_container_width=True, key="guardar_impresion_copy_mary"):
        try:
            orden_id = guardar_costeo(
                usuario=usuario,
                tipo_proceso="Impresión",
                descripcion=descripcion,
                cantidad=float(cantidad_val),
                costo_materiales_usd=round((float(costo_papel_hoja) + float(costo_tinta_hoja) + float(costo_cabezal_hoja)) * cantidad_val, 2),
                costo_mano_obra_usd=round(float(mano_obra_hoja) * cantidad_val, 2),
                costo_indirecto_usd=round((float(indirectos_hoja) + float(costo_merma_hoja)) * cantidad_val, 2),
                margen_pct=float(margen_pct),
                precio_sugerido_usd=float(precio_recomendado_total),
                origen="calculadora_impresion_copy_mary",
                detalle=[
                    {"categoria": "papel", "concepto": papel, "cantidad": cantidad_val, "costo_unitario_usd": float(costo_papel_hoja), "subtotal_usd": round(float(costo_papel_hoja) * cantidad_val, 2)},
                    {"categoria": "tinta", "concepto": tipo_impresion, "cantidad": cantidad_val, "costo_unitario_usd": float(costo_tinta_hoja), "subtotal_usd": round(float(costo_tinta_hoja) * cantidad_val, 2)},
                    {"categoria": "cabezal", "concepto": "Desgaste de cabezal", "cantidad": cantidad_val, "costo_unitario_usd": float(costo_cabezal_hoja), "subtotal_usd": round(float(costo_cabezal_hoja) * cantidad_val, 2)},
                    {"categoria": "mano_obra", "concepto": "Mano de obra", "cantidad": cantidad_val, "costo_unitario_usd": float(mano_obra_hoja), "subtotal_usd": round(float(mano_obra_hoja) * cantidad_val, 2)},
                    {"categoria": "indirecto", "concepto": "Servicios e indirectos", "cantidad": cantidad_val, "costo_unitario_usd": float(indirectos_hoja), "subtotal_usd": round(float(indirectos_hoja) * cantidad_val, 2)},
                    {"categoria": "merma", "concepto": "Merma estimada", "cantidad": cantidad_val, "costo_unitario_usd": float(costo_merma_hoja), "subtotal_usd": round(float(costo_merma_hoja) * cantidad_val, 2)},
                ],
            )
            st.success(f"Cálculo de impresión guardado como costeo #{orden_id}.")
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo guardar el cálculo de impresión: {exc}")


def render_costeo(usuario: str) -> None:
    st.title("🧮 Costeo unificado")
    st.caption(
        "Calcula costo estimado, margen, precio sugerido y registra el costo real para análisis de desviaciones."
    )

    parametros = obtener_parametros_costeo() or {}

    with st.expander("⚙️ Parámetros base activos", expanded=False):
        c1, c2, c3 = st.columns(3)
        c1.metric("Imprevistos", f"{float(parametros.get('factor_imprevistos_pct', 0.0)):.1f}%")
        c2.metric("Indirecto", f"{float(parametros.get('factor_indirecto_pct', 0.0)):.1f}%")
        c3.metric("Margen objetivo", f"{float(parametros.get('margen_objetivo_pct', 35.0)):.1f}%")

    tab_impresion, tab_general, tab_cierre, tab_historial = st.tabs(
        ["🖨️ Impresión Copy Mary", "📐 Costeo general", "🏁 Cierre real", "🗂 Historial"]
    )

    with tab_impresion:
        _render_calculadora_impresion_copy_mary(usuario, parametros)

    with tab_general:
        st.subheader("📐 Costeo estimado")

        with st.form("costeo_form"):
            tipo = st.selectbox("Tipo de proceso", TIPOS_PROCESO)
            descripcion = st.text_input("Descripción", placeholder="Ej: Banner 2x1 + instalación")

            c1, c2 = st.columns(2)
            with c1:
                cantidad = st.number_input("Cantidad", min_value=0.01, value=1.0, step=1.0, format="%.2f")
                costo_materiales = st.number_input(
                    "Costo materiales (USD)",
                    min_value=0.0,
                    value=10.0,
                    step=0.5,
                    format="%.2f",
                )
            with c2:
                costo_mano_obra = st.number_input(
                    "Costo mano de obra (USD)",
                    min_value=0.0,
                    value=5.0,
                    step=0.5,
                    format="%.2f",
                )
                costo_indirecto = st.number_input(
                    "Costo indirecto directo (USD)",
                    min_value=0.0,
                    value=2.0,
                    step=0.5,
                    format="%.2f",
                )

            margen_pct = st.number_input(
                "Margen objetivo (%)",
                min_value=0.0,
                max_value=300.0,
                value=float(parametros.get("margen_objetivo_pct", 35.0)),
                step=1.0,
                format="%.2f",
            )

            submitted = st.form_submit_button("Calcular costo + precio sugerido", use_container_width=True)

        if submitted:
            try:
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
            except Exception as exc:
                st.error(f"No se pudo calcular el costeo: {exc}")
                return

        actual = st.session_state.get("costeo_actual")
        if not actual:
            st.info("Ingresa parámetros y ejecuta el cálculo para ver desglose, margen y precio sugerido.")
        else:
            costo_data = actual["costo_data"]
            margen_data = actual["margen_data"]
            desglose_df = _df_desglose(costo_data)

            st.markdown("### 📋 Desglose del costo")
            st.dataframe(
                desglose_df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "subtotal_usd": st.column_config.NumberColumn("Subtotal USD", format="%.2f"),
                },
            )

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Costo total", f"$ {float(costo_data.get('costo_total_usd', 0.0)):,.2f}")
            m2.metric("Costo unitario", f"$ {float(costo_data.get('costo_unitario_usd', 0.0)):,.2f}")
            m3.metric("Margen estimado", f"{float(margen_data.get('margen_estimado_pct', 0.0)):,.2f}%")
            m4.metric("Precio sugerido", f"$ {float(margen_data.get('precio_sugerido_usd', 0.0)):,.2f}")

            if st.button("💾 Guardar cálculo", use_container_width=True, key="costeo_guardar"):
                try:
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
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo guardar el costeo: {exc}")

    with tab_cierre:
        st.subheader("🏁 Cierre de costeo real")

        historial_cierre = listar_costeos(limit=100)
        if historial_cierre is None or historial_cierre.empty:
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
                materiales_real = c1.number_input(
                    "Materiales consumidos (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                )
                merma_real = c2.number_input(
                    "Merma (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                )
                mano_obra_real = c3.number_input(
                    "Mano de obra real (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                )

                c4, c5, c6 = st.columns(3)
                tiempo_real = c4.number_input(
                    "Tiempo real (horas)",
                    min_value=0.0,
                    value=0.0,
                    step=0.25,
                    format="%.2f",
                )
                energia_real = c5.number_input(
                    "Energía / indirectos reales (USD)",
                    min_value=0.0,
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                )
                ajustes_real = c6.number_input(
                    "Ajustes manuales (USD)",
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                )

                c7, c8, c9 = st.columns(3)
                precio_vendido = c7.number_input(
                    "Precio vendido (USD, opcional)",
                    min_value=0.0,
                    value=0.0,
                    step=0.5,
                    format="%.2f",
                )
                venta_id = c8.number_input("ID venta (opcional)", min_value=0, value=0, step=1)
                orden_prod_id = c9.number_input("ID orden producción (opcional)", min_value=0, value=0, step=1)

                cerrar_directo = st.checkbox("Cerrar costeo ahora", value=True)

                submit_cierre = st.form_submit_button("Registrar costo real", use_container_width=True)

            if submit_cierre:
                try:
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
                        f"Costo real: $ {float(resultado.get('costo_real_usd', 0.0)):,.2f} · "
                        f"Margen real: {float(resultado.get('margen_real_pct', 0.0)):,.2f}% · "
                        f"Δ vs estimado: $ {float(resultado.get('diferencia_vs_estimado_usd', 0.0)):,.2f}"
                    )
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar el costeo real: {exc}")

    with tab_historial:
        st.subheader("🗂 Historial de costeos")

        historial = listar_costeos(limit=20)
        if historial is None or historial.empty:
            st.info("Aún no hay costeos guardados.")
        else:
            st.dataframe(
                historial,
                use_container_width=True,
                hide_index=True,
            )

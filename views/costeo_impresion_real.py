from __future__ import annotations

import pandas as pd
import streamlit as st

from services.costeo_impresion_historial_service import (
    guardar_costeo_impresion_real,
    listar_costeos_impresion_real,
)
from services.costeo_impresion_real_service import calcular_costo_impresion_real
from services.impresora_consumibles_service import listar_impresoras_activas


def _label_impresora(row: pd.Series) -> str:
    modelo = str(row.get("modelo") or "").strip()
    tipo = str(row.get("tipo_detalle") or "").strip()
    label = f"#{int(row['id'])} · {row.get('equipo')}"
    if modelo:
        label += f" ({modelo})"
    if tipo:
        label += f" · {tipo}"
    return label


def _precio_con_margen(costo: float, margen_pct: float) -> float:
    margen = max(0.0, float(margen_pct or 0.0)) / 100.0
    if margen >= 0.95:
        margen = 0.95
    return float(costo) / max(1.0 - margen, 0.05)


def render_costeo_impresion_real(usuario: str) -> None:
    st.subheader("🖨️ Costeo real por impresora")
    st.caption(
        "Calcula el costo técnico usando los consumibles asociados en Activos → Consumibles por impresora. "
        "Luego suma papel, servicios, mano de obra, depreciación y margen para sugerir precio final."
    )

    impresoras = listar_impresoras_activas()
    if impresoras.empty:
        st.warning("Primero registra tus impresoras en Activos y asocia sus consumibles.")
        return

    opciones = {_label_impresora(row): int(row["id"]) for _, row in impresoras.iterrows()}
    impresora_label = st.selectbox("Impresora", list(opciones.keys()), key="costeo_real_impresora")
    impresora_id = opciones[impresora_label]

    st.markdown("##### Trabajo")
    c1, c2, c3 = st.columns(3)
    paginas = c1.number_input("Páginas / unidades del trabajo", min_value=1.0, value=1.0, step=1.0)
    copias = c2.number_input("Copias del trabajo", min_value=1.0, value=1.0, step=1.0)
    paginas_totales = float(paginas) * float(copias)
    c3.metric("Total páginas/unidades", f"{paginas_totales:,.0f}")

    st.markdown("##### Papel / material directo")
    p1, p2, p3 = st.columns(3)
    costo_papel_unidad = p1.number_input("Costo papel/material por unidad USD", min_value=0.0, value=0.0, step=0.001, format="%.4f")
    merma_pct = p2.number_input("Merma %", min_value=0.0, value=0.0, step=1.0)
    otros_materiales = p3.number_input("Otros materiales USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")

    st.markdown("##### Servicios, mano de obra y depreciación")
    s1, s2, s3, s4 = st.columns(4)
    electricidad = s1.number_input("Electricidad USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")
    internet = s2.number_input("Internet/servicios USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")
    mano_obra = s3.number_input("Mano de obra USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")
    depreciacion = s4.number_input("Depreciación equipo USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")

    st.markdown("##### Cabezales")
    incluir_cabezales = st.checkbox("Incluir desgaste de cabezales", value=False)
    cantidad_cabezales = 0.0
    costo_unitario_cabezal = 0.0
    vida_util_cabezales = 0.0
    impuestos_cabezales = 0.0
    delivery_cabezales = 0.0
    comision_cabezales = 0.0

    if incluir_cabezales:
        h1, h2, h3 = st.columns(3)
        cantidad_cabezales = h1.number_input("Cantidad de cabezales", min_value=0.0, value=2.0, step=1.0)
        costo_unitario_cabezal = h2.number_input("Costo por cabezal USD", min_value=0.0, value=50.0, step=1.0)
        vida_util_cabezales = h3.number_input("Vida útil estimada en páginas", min_value=0.0, value=12000.0, step=500.0)

        h4, h5, h6 = st.columns(3)
        impuestos_cabezales = h4.number_input("Impuestos cabezales %", min_value=0.0, value=0.0, step=1.0)
        delivery_cabezales = h5.number_input("Delivery cabezales USD", min_value=0.0, value=0.0, step=1.0)
        comision_cabezales = h6.number_input("Comisión pago cabezales USD", min_value=0.0, value=0.0, step=1.0)

    st.markdown("##### Precio y margen")
    m1, m2 = st.columns(2)
    margen_pct = m1.number_input("Margen deseado %", min_value=0.0, value=40.0, step=1.0)
    redondeo_bs = m2.number_input("Redondeo manual / referencia Bs", min_value=0.0, value=0.0, step=1.0)

    if st.button("Calcular precio sugerido", use_container_width=True):
        try:
            resultado = calcular_costo_impresion_real(
                activo_id=impresora_id,
                paginas=float(paginas_totales),
                incluir_cabezales=bool(incluir_cabezales),
                cantidad_cabezales=float(cantidad_cabezales),
                costo_unitario_cabezal_usd=float(costo_unitario_cabezal),
                vida_util_cabezales_paginas=float(vida_util_cabezales),
                impuestos_cabezales_pct=float(impuestos_cabezales),
                delivery_cabezales_usd=float(delivery_cabezales),
                comision_cabezales_usd=float(comision_cabezales),
            )
        except Exception as exc:
            st.error(f"No se pudo calcular: {exc}")
            return

        costo_papel_total = float(costo_papel_unidad) * paginas_totales
        costo_merma = costo_papel_total * (float(merma_pct or 0.0) / 100.0)
        costos_operativos = float(electricidad) + float(internet) + float(mano_obra) + float(depreciacion)
        costo_total = (
            resultado.costo_total_tecnico_usd
            + costo_papel_total
            + costo_merma
            + float(otros_materiales)
            + costos_operativos
        )
        precio_sugerido = _precio_con_margen(costo_total, float(margen_pct))
        ganancia = precio_sugerido - costo_total
        precio_unitario = precio_sugerido / paginas_totales if paginas_totales > 0 else 0.0

        st.session_state["ultimo_costeo_impresion_real"] = {
            "usuario": usuario,
            "activo_id": impresora_id,
            "impresora_label": impresora_label,
            "paginas": paginas_totales,
            "costo_consumibles_usd": resultado.costo_consumibles_usd,
            "costo_cabezales_usd": resultado.costo_cabezales_usd,
            "costo_papel_usd": costo_papel_total,
            "costo_merma_usd": costo_merma,
            "otros_materiales_usd": float(otros_materiales),
            "electricidad_usd": float(electricidad),
            "internet_usd": float(internet),
            "mano_obra_usd": float(mano_obra),
            "depreciacion_usd": float(depreciacion),
            "costo_total_usd": costo_total,
            "margen_pct": float(margen_pct),
            "precio_sugerido_usd": precio_sugerido,
            "precio_unitario_usd": precio_unitario,
            "ganancia_usd": ganancia,
            "detalle": resultado.detalle,
        }

        r1, r2, r3, r4 = st.columns(4)
        r1.metric("Costo técnico", f"${resultado.costo_total_tecnico_usd:,.4f}")
        r2.metric("Costo total", f"${costo_total:,.4f}")
        r3.metric("Precio sugerido", f"${precio_sugerido:,.4f}")
        r4.metric("Precio por unidad", f"${precio_unitario:,.4f}")

        r5, r6, r7, r8 = st.columns(4)
        r5.metric("Ganancia estimada", f"${ganancia:,.4f}")
        r6.metric("Consumibles", f"${resultado.costo_consumibles_usd:,.4f}")
        r7.metric("Cabezales", f"${resultado.costo_cabezales_usd:,.4f}")
        r8.metric("Papel/material", f"${(costo_papel_total + costo_merma):,.4f}")

        resumen = pd.DataFrame(
            [
                {"concepto": "Consumibles máquina", "costo_usd": resultado.costo_consumibles_usd},
                {"concepto": "Cabezales", "costo_usd": resultado.costo_cabezales_usd},
                {"concepto": "Papel/material", "costo_usd": round(costo_papel_total, 6)},
                {"concepto": "Merma", "costo_usd": round(costo_merma, 6)},
                {"concepto": "Otros materiales", "costo_usd": round(float(otros_materiales), 6)},
                {"concepto": "Electricidad", "costo_usd": round(float(electricidad), 6)},
                {"concepto": "Internet/servicios", "costo_usd": round(float(internet), 6)},
                {"concepto": "Mano de obra", "costo_usd": round(float(mano_obra), 6)},
                {"concepto": "Depreciación", "costo_usd": round(float(depreciacion), 6)},
                {"concepto": "Costo total", "costo_usd": round(costo_total, 6)},
                {"concepto": "Precio sugerido", "costo_usd": round(precio_sugerido, 6)},
            ]
        )
        st.dataframe(resumen, use_container_width=True, hide_index=True)

        if redondeo_bs > 0:
            st.info(f"Referencia manual de redondeo en Bs: {redondeo_bs:,.2f} Bs")

        if resultado.detalle:
            with st.expander("Detalle técnico de consumibles"):
                st.dataframe(pd.DataFrame(resultado.detalle), use_container_width=True, hide_index=True)
        else:
            st.warning("Esta impresora no tiene consumibles asociados o no tienen costo/rendimiento suficiente.")

    ultimo = st.session_state.get("ultimo_costeo_impresion_real")
    if ultimo:
        if st.button("💾 Guardar costeo calculado", use_container_width=True):
            try:
                costeo_id = guardar_costeo_impresion_real(**ultimo)
                st.success(f"Costeo guardado con ID #{costeo_id}.")
                st.session_state.pop("ultimo_costeo_impresion_real", None)
            except Exception as exc:
                st.error(f"No se pudo guardar el costeo: {exc}")

    st.markdown("##### Historial reciente")
    try:
        historial = listar_costeos_impresion_real(limit=25)
        if historial.empty:
            st.caption("Aún no hay costeos reales guardados.")
        else:
            st.dataframe(historial, use_container_width=True, hide_index=True)
    except Exception as exc:
        st.warning(f"No se pudo cargar el historial: {exc}")

    st.caption(f"Usuario: {usuario}")

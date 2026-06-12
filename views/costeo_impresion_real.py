from __future__ import annotations

import pandas as pd
import streamlit as st

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


def render_costeo_impresion_real(usuario: str) -> None:
    st.subheader("🖨️ Costeo real por impresora")
    st.caption(
        "Calcula el costo técnico usando los consumibles asociados en Activos → Consumibles por impresora. "
        "Este cálculo incluye tinta, cartuchos, tóner, rollos, ribbon y cabezales si los activas."
    )

    impresoras = listar_impresoras_activas()
    if impresoras.empty:
        st.warning("Primero registra tus impresoras en Activos y asocia sus consumibles.")
        return

    opciones = {_label_impresora(row): int(row["id"]) for _, row in impresoras.iterrows()}
    impresora_label = st.selectbox("Impresora", list(opciones.keys()), key="costeo_real_impresora")
    impresora_id = opciones[impresora_label]

    c1, c2 = st.columns(2)
    paginas = c1.number_input("Páginas / unidades del trabajo", min_value=1.0, value=1.0, step=1.0)
    incluir_cabezales = c2.checkbox("Incluir desgaste de cabezales", value=False)

    cantidad_cabezales = 0.0
    costo_unitario_cabezal = 0.0
    vida_util_cabezales = 0.0
    impuestos_cabezales = 0.0
    delivery_cabezales = 0.0
    comision_cabezales = 0.0

    if incluir_cabezales:
        st.markdown("##### Cabezales")
        h1, h2, h3 = st.columns(3)
        cantidad_cabezales = h1.number_input("Cantidad de cabezales", min_value=0.0, value=2.0, step=1.0)
        costo_unitario_cabezal = h2.number_input("Costo por cabezal USD", min_value=0.0, value=50.0, step=1.0)
        vida_util_cabezales = h3.number_input("Vida útil estimada en páginas", min_value=0.0, value=12000.0, step=500.0)

        h4, h5, h6 = st.columns(3)
        impuestos_cabezales = h4.number_input("Impuestos cabezales %", min_value=0.0, value=0.0, step=1.0)
        delivery_cabezales = h5.number_input("Delivery cabezales USD", min_value=0.0, value=0.0, step=1.0)
        comision_cabezales = h6.number_input("Comisión pago cabezales USD", min_value=0.0, value=0.0, step=1.0)

    if st.button("Calcular costo técnico", use_container_width=True):
        try:
            resultado = calcular_costo_impresion_real(
                activo_id=impresora_id,
                paginas=float(paginas),
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

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Consumibles", f"${resultado.costo_consumibles_usd:,.4f}")
        m2.metric("Cabezales", f"${resultado.costo_cabezales_usd:,.4f}")
        m3.metric("Costo técnico total", f"${resultado.costo_total_tecnico_usd:,.4f}")
        m4.metric("Costo técnico por página", f"${resultado.costo_por_pagina_usd:,.6f}")

        if resultado.detalle:
            st.dataframe(pd.DataFrame(resultado.detalle), use_container_width=True, hide_index=True)
        else:
            st.info("Esta impresora no tiene consumibles asociados o no tienen costo/rendimiento suficiente.")

    st.caption(f"Usuario: {usuario}")

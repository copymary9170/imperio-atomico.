from __future__ import annotations

import pandas as pd
import streamlit as st

from services.impresora_consumibles_service import (
    COLORES_CONSUMIBLE,
    TIPOS_CONSUMIBLE,
    asignar_consumible_impresora,
    desactivar_consumible_impresora,
    listar_consumibles_inventario,
    listar_consumibles_por_impresora,
    listar_impresoras_activas,
)


def _label_impresora(row: pd.Series) -> str:
    modelo = str(row.get("modelo") or "").strip()
    tipo = str(row.get("tipo_detalle") or "").strip()
    partes = [f"#{int(row['id'])} · {row.get('equipo')}"]
    if modelo:
        partes.append(f"({modelo})")
    if tipo:
        partes.append(f"· {tipo}")
    return " ".join(partes)


def _label_consumible(row: pd.Series) -> str:
    sku = str(row.get("sku") or "").strip()
    categoria = str(row.get("categoria") or "").strip()
    nombre = str(row.get("nombre") or "").strip()
    costo = float(row.get("costo_unitario_usd") or 0.0)
    stock = float(row.get("stock_actual") or 0.0)
    base = f"#{int(row['id'])} · {nombre}"
    if sku:
        base += f" · SKU {sku}"
    if categoria:
        base += f" · {categoria}"
    base += f" · Stock {stock:g} · Costo ${costo:,.4f}"
    return base


def render_impresora_consumibles(usuario: str) -> None:
    st.subheader("🔗 Consumibles por impresora")
    st.caption(
        "Asocia cada impresora registrada en Activos con sus tintas, cartuchos, tóneres o cabezales registrados en Inventario. "
        "La calculadora de impresión usará esta relación para no mezclar consumibles entre máquinas."
    )

    impresoras = listar_impresoras_activas()
    consumibles = listar_consumibles_inventario()

    if impresoras.empty:
        st.warning("Primero registra tus impresoras en Activos con unidad 'Impresora'.")
        return
    if consumibles.empty:
        st.warning("Primero registra tintas, cartuchos o materiales en Inventario.")
        return

    opciones_impresoras = {_label_impresora(row): int(row["id"]) for _, row in impresoras.iterrows()}
    impresora_label = st.selectbox("Impresora", list(opciones_impresoras.keys()), key="impresora_consumibles_impresora")
    impresora_id = opciones_impresoras[impresora_label]

    tab_asignar, tab_actuales = st.tabs(["➕ Asignar consumible", "📋 Consumibles actuales"])

    with tab_asignar:
        opciones_consumibles = {_label_consumible(row): int(row["id"]) for _, row in consumibles.iterrows()}
        with st.form("form_asignar_consumible_impresora"):
            consumible_label = st.selectbox("Consumible de inventario", list(opciones_consumibles.keys()))
            c1, c2 = st.columns(2)
            tipo = c1.selectbox("Tipo de consumible", TIPOS_CONSUMIBLE)
            color = c2.selectbox("Color / canal", COLORES_CONSUMIBLE)

            c3, c4 = st.columns(2)
            rendimiento = c3.number_input(
                "Rendimiento estimado en páginas",
                min_value=0.0,
                value=0.0,
                step=100.0,
                format="%.2f",
                help="Ejemplo: 12000 páginas para negro en tanque, 6000 para color, o el rendimiento del cartucho/tóner.",
            )
            costo_hoja = c4.number_input(
                "Costo estimado por hoja (USD)",
                min_value=0.0,
                value=0.0,
                step=0.001,
                format="%.4f",
                help="Opcional. Si lo dejas en 0, luego la calculadora podrá estimarlo usando costo y rendimiento.",
            )

            cobertura = st.text_input(
                "Cobertura de referencia",
                placeholder="Ej: 5%, ISO, foto completa, estimado manual",
            )
            notas = st.text_area(
                "Notas",
                placeholder="Ej: tinta negra compatible con HP 580; usar solo para documentos B/N.",
            )
            submitted = st.form_submit_button("Guardar relación", use_container_width=True)

        if submitted:
            try:
                relacion_id = asignar_consumible_impresora(
                    activo_id=impresora_id,
                    inventario_id=opciones_consumibles[consumible_label],
                    tipo_consumible=tipo,
                    color=color,
                    rendimiento_paginas=float(rendimiento),
                    cobertura_referencia=cobertura,
                    costo_estimado_hoja_usd=float(costo_hoja),
                    notas=notas,
                )
                st.success(f"Consumible asociado correctamente. Relación #{relacion_id}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo asociar el consumible: {exc}")

    with tab_actuales:
        actuales = listar_consumibles_por_impresora(impresora_id)
        if actuales.empty:
            st.info("Esta impresora todavía no tiene consumibles asociados.")
            return

        vista = actuales[
            [
                "id",
                "consumible",
                "sku",
                "categoria_consumible",
                "tipo_consumible",
                "color",
                "rendimiento_paginas",
                "cobertura_referencia",
                "costo_estimado_hoja_usd",
                "stock_actual",
                "costo_unitario_usd",
                "notas",
            ]
        ].copy()
        st.dataframe(
            vista,
            use_container_width=True,
            hide_index=True,
            column_config={
                "costo_estimado_hoja_usd": st.column_config.NumberColumn("Costo hoja USD", format="%.4f"),
                "costo_unitario_usd": st.column_config.NumberColumn("Costo inventario USD", format="%.4f"),
                "stock_actual": st.column_config.NumberColumn("Stock", format="%.2f"),
                "rendimiento_paginas": st.column_config.NumberColumn("Rendimiento", format="%.2f"),
            },
        )

        ids = [int(x) for x in actuales["id"].tolist()]
        relacion_id = st.selectbox("Relación a desactivar", ids, key="desactivar_relacion_impresora_consumible")
        if st.button("Desactivar relación seleccionada", use_container_width=True):
            try:
                desactivar_consumible_impresora(int(relacion_id))
                st.success("Relación desactivada.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo desactivar la relación: {exc}")

    st.caption(f"Configuración actualizada por: {usuario}")

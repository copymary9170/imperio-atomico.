from __future__ import annotations

import pandas as pd
import streamlit as st

from services.costo_real_compra_service import calcular_costo_real_compra
from services.materia_prima_service import (
    MATERIA_PRIMA_CATEGORIAS,
    UNIDADES_MATERIA_PRIMA,
    crear_materia_prima,
    listar_compras_materia_prima,
    listar_materia_prima,
    registrar_compra_materia_prima,
)


def _label_item(row: pd.Series) -> str:
    return f"#{int(row['id'])} · {row['nombre']} · stock {float(row['stock_actual'] or 0):g} {row['unidad']} · costo ${float(row['costo_unitario_usd'] or 0):,.4f}"


def render_materia_prima(usuario: str) -> None:
    st.subheader("📦 Materia prima")
    st.caption(
        "Aquí se registran insumos comprados para producir: papel, tinta, tóner, cartuchos, opalina, acetato, rollos, vinil, empaques y similares. "
        "Las compras incluyen cantidad comprada, stock actual, delivery, impuestos, comisión y método de pago."
    )

    tab_existencias, tab_crear, tab_compra, tab_historial = st.tabs([
        "Existencias",
        "Crear materia prima",
        "Registrar compra",
        "Historial de compras",
    ])

    with tab_existencias:
        df = listar_materia_prima()
        if df.empty:
            st.info("Aún no hay materia prima registrada.")
        else:
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "stock_actual": st.column_config.NumberColumn("Stock actual", format="%.4f"),
                    "stock_minimo": st.column_config.NumberColumn("Stock mínimo", format="%.4f"),
                    "costo_unitario_usd": st.column_config.NumberColumn("Costo promedio USD", format="%.6f"),
                    "precio_venta_usd": st.column_config.NumberColumn("Precio venta USD", format="%.4f"),
                },
            )

    with tab_crear:
        st.markdown("##### Crear insumo")
        with st.form("form_crear_materia_prima"):
            c1, c2, c3 = st.columns(3)
            sku = c1.text_input("SKU", placeholder="MP-BOND-CARTA")
            nombre = c2.text_input("Nombre", placeholder="Papel bond carta")
            categoria = c3.selectbox("Categoría", MATERIA_PRIMA_CATEGORIAS)

            c4, c5, c6 = st.columns(3)
            unidad = c4.selectbox("Unidad de inventario", UNIDADES_MATERIA_PRIMA)
            stock_minimo = c5.number_input("Stock mínimo", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            precio_venta = c6.number_input("Precio de venta opcional USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")

            submitted = st.form_submit_button("Crear materia prima", use_container_width=True)
        if submitted:
            try:
                item_id = crear_materia_prima(
                    usuario=usuario,
                    sku=sku,
                    nombre=nombre,
                    categoria=categoria,
                    unidad=unidad,
                    stock_minimo=float(stock_minimo),
                    precio_venta_usd=float(precio_venta),
                )
                st.success(f"Materia prima creada con ID #{item_id}. Ahora registra su compra para cargar stock y costo real.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear la materia prima: {exc}")

    with tab_compra:
        st.markdown("##### Registrar compra con costo real")
        df = listar_materia_prima()
        if df.empty:
            st.warning("Primero crea una materia prima en la pestaña anterior.")
        else:
            opciones = {_label_item(row): int(row["id"]) for _, row in df.iterrows()}
            item_label = st.selectbox("Materia prima", list(opciones.keys()))
            item_id = opciones[item_label]

            with st.form("form_compra_materia_prima"):
                c1, c2, c3 = st.columns(3)
                cantidad = c1.number_input("Cantidad comprada", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
                costo_base = c2.number_input("Costo base total USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                impuestos_pct = c3.number_input("Impuestos %", min_value=0.0, value=0.0, step=1.0, format="%.4f")

                c4, c5, c6 = st.columns(3)
                delivery = c4.number_input("Delivery / envío USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                comision = c5.number_input("Comisión de pago USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")
                moneda = c6.selectbox("Moneda de pago", ["USD", "Bs", "COP", "EUR"])

                c7, c8, c9 = st.columns(3)
                tasa = c7.number_input("Tasa de cambio", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
                metodo_pago = c8.selectbox("Método de pago", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
                tipo_pago = c9.selectbox("Tipo de pago", ["contado", "credito", "parcial"])

                monto_inicial = st.number_input("Monto pagado inicial USD", min_value=0.0, value=0.0, step=1.0, format="%.4f", help="Déjalo en 0 para registrar saldo pendiente. Si pagaste todo, coloca el total real o deja que el sistema lo calcule después.")
                referencia = st.text_input("Referencia / nota", placeholder="Factura, proveedor, número de pago, etc.")

                if costo_base > 0 and cantidad > 0:
                    previo = calcular_costo_real_compra(
                        costo_base_usd=float(costo_base),
                        cantidad=float(cantidad),
                        impuestos_pct=float(impuestos_pct),
                        delivery_usd=float(delivery),
                        comision_pago_usd=float(comision),
                    )
                    p1, p2, p3, p4 = st.columns(4)
                    p1.metric("Total real", f"${previo.total_real_usd:,.4f}")
                    p2.metric("Costo unitario real", f"${previo.costo_unitario_real_usd:,.6f}")
                    p3.metric("Impuesto USD", f"${previo.impuesto_usd:,.4f}")
                    p4.metric("Delivery + comisión", f"${(previo.delivery_usd + previo.comision_pago_usd):,.4f}")

                submitted = st.form_submit_button("Registrar compra y actualizar stock", use_container_width=True)

            if submitted:
                try:
                    resultado = registrar_compra_materia_prima(
                        usuario=usuario,
                        inventario_id=int(item_id),
                        cantidad_comprada=float(cantidad),
                        costo_base_usd=float(costo_base),
                        impuestos_pct=float(impuestos_pct),
                        delivery_usd=float(delivery),
                        comision_pago_usd=float(comision),
                        moneda_pago=moneda,
                        tasa_cambio=float(tasa),
                        metodo_pago=metodo_pago,
                        tipo_pago=tipo_pago,
                        monto_pagado_inicial_usd=float(monto_inicial) if float(monto_inicial) > 0 else None,
                        referencia=referencia,
                    )
                    st.success(f"Compra #{resultado['compra_id']} registrada. Stock: {resultado['stock_anterior']} + {resultado['cantidad_comprada']} = {resultado['stock_nuevo']}.")
                    st.info(f"Costo unitario real: ${resultado['costo_unitario_real_usd']:,.6f} · Costo promedio nuevo: ${resultado['costo_promedio_usd']:,.6f}")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar la compra: {exc}")

    with tab_historial:
        st.markdown("##### Historial de compras de materia prima")
        try:
            compras = listar_compras_materia_prima(limit=100)
            if compras.empty:
                st.info("Aún no hay compras registradas.")
            else:
                st.dataframe(
                    compras,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "cantidad": st.column_config.NumberColumn("Cantidad comprada", format="%.4f"),
                        "stock_actual": st.column_config.NumberColumn("Stock actual", format="%.4f"),
                        "costo_total_usd": st.column_config.NumberColumn("Total real USD", format="%.4f"),
                        "costo_unit_usd": st.column_config.NumberColumn("Costo unitario real", format="%.6f"),
                        "delivery": st.column_config.NumberColumn("Delivery", format="%.4f"),
                        "comision_pago_usd": st.column_config.NumberColumn("Comisión", format="%.4f"),
                        "costo_promedio_actual": st.column_config.NumberColumn("Costo promedio actual", format="%.6f"),
                    },
                )
        except Exception as exc:
            st.error(f"No se pudo cargar el historial: {exc}")

    st.caption(f"Usuario: {usuario}")

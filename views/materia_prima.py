from __future__ import annotations

import pandas as pd
import streamlit as st

from services.costo_real_compra_service import calcular_costo_real_compra
from services.materia_prima_service import (
    MATERIA_PRIMA_CATEGORIAS,
    UNIDADES_MATERIA_PRIMA,
    UNIDADES_TECNICAS,
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
        "Aquí se registran insumos comprados para producir. El stock físico se lleva en unidades reales de compra "
        "como botella, resma, rollo, caja o cartucho. La unidad técnica como ml, gr o cm queda separada para costeo y merma."
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
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_crear:
        st.markdown("##### Crear ficha maestra de materia prima")
        with st.form("form_crear_materia_prima"):
            c1, c2, c3 = st.columns(3)
            sku = c1.text_input("SKU", placeholder="MP-TINTA-GT52-C")
            nombre = c2.text_input("Nombre", placeholder="Tinta HP GT52 Cyan")
            categoria = c3.selectbox("Categoría", MATERIA_PRIMA_CATEGORIAS)

            c4, c5, c6 = st.columns(3)
            proveedor_principal = c4.text_input("Proveedor principal")
            proveedor_alternativo = c5.text_input("Proveedor alternativo")
            marca = c6.text_input("Marca", placeholder="HP, Epson, Amiko...")

            c7, c8, c9 = st.columns(3)
            fabricante = c7.text_input("Fabricante")
            codigo_fabricante = c8.text_input("Código fabricante")
            ubicacion = c9.text_input("Ubicación", placeholder="Estante A, gaveta 2...")

            st.markdown("###### Inventario físico")
            i1, i2, i3, i4 = st.columns(4)
            unidad = i1.selectbox("Unidad de inventario", UNIDADES_MATERIA_PRIMA, help="La unidad física que realmente cuentas: botella, rollo, resma, caja, cartucho...")
            stock_minimo = i2.number_input("Stock mínimo", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            stock_maximo = i3.number_input("Stock máximo", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            precio_venta = i4.number_input("Precio venta opcional USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")

            st.markdown("###### Unidad técnica para costeo / merma")
            t1, t2, t3 = st.columns(3)
            unidad_tecnica = t1.selectbox("Unidad técnica", UNIDADES_TECNICAS, help="No es el stock principal. Sirve para costeo o merma: ml, gr, cm, metros, hojas...")
            contenido_tecnico = t2.number_input("Contenido técnico por unidad", min_value=0.0, value=0.0, step=1.0, format="%.4f", help="Ejemplo: 1 botella = 70 ml; 1 rollo = 500 cm; 1 resma = 500 hojas.")
            rendimiento_estimado = t3.number_input("Rendimiento estimado", min_value=0.0, value=0.0, step=1.0, format="%.4f", help="Ejemplo: páginas estimadas, etiquetas, impresiones, etc.")

            compatible_con = st.text_area("Compatible con / notas técnicas", placeholder="HP Smart Tank 580, Epson L3250, papel fotográfico, etc.")

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
                    proveedor_principal=proveedor_principal,
                    proveedor_alternativo=proveedor_alternativo,
                    marca=marca,
                    fabricante=fabricante,
                    codigo_fabricante=codigo_fabricante,
                    ubicacion=ubicacion,
                    stock_maximo=float(stock_maximo),
                    unidad_tecnica=unidad_tecnica,
                    contenido_tecnico=float(contenido_tecnico),
                    rendimiento_estimado=float(rendimiento_estimado),
                    compatible_con=compatible_con,
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
                c0, c00, c000 = st.columns(3)
                proveedor = c0.text_input("Proveedor de esta compra")
                factura = c00.text_input("Factura / comprobante")
                referencia = c000.text_input("Referencia / nota")

                c1, c2, c3 = st.columns(3)
                cantidad = c1.number_input("Cantidad comprada", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
                costo_base = c2.number_input("Costo base total USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                impuestos_pct = c3.number_input("Impuestos %", min_value=0.0, value=0.0, step=1.0, format="%.4f")

                c4, c5, c6, c66 = st.columns(4)
                delivery = c4.number_input("Delivery / envío USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                comision = c5.number_input("Comisión de pago USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")
                otros_gastos = c6.number_input("Otros gastos USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")
                moneda = c66.selectbox("Moneda de pago", ["USD", "Bs", "COP", "EUR"])

                c7, c8, c9 = st.columns(3)
                tasa = c7.number_input("Tasa de cambio", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
                metodo_pago = c8.selectbox("Método de pago", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"])
                tipo_pago = c9.selectbox("Tipo de pago", ["contado", "credito", "parcial"])

                monto_inicial = st.number_input("Monto pagado inicial USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")

                if costo_base > 0 and cantidad > 0:
                    previo = calcular_costo_real_compra(
                        costo_base_usd=float(costo_base) + float(otros_gastos),
                        cantidad=float(cantidad),
                        impuestos_pct=float(impuestos_pct),
                        delivery_usd=float(delivery),
                        comision_pago_usd=float(comision),
                    )
                    p1, p2, p3, p4 = st.columns(4)
                    p1.metric("Total real", f"${previo.total_real_usd:,.4f}")
                    p2.metric("Costo unitario real", f"${previo.costo_unitario_real_usd:,.6f}")
                    p3.metric("Impuesto USD", f"${previo.impuesto_usd:,.4f}")
                    p4.metric("Delivery + comisión + otros", f"${(previo.delivery_usd + previo.comision_pago_usd + float(otros_gastos)):,.4f}")

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
                        proveedor=proveedor,
                        factura=factura,
                        otros_gastos_usd=float(otros_gastos),
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
                st.dataframe(compras, use_container_width=True, hide_index=True)
        except Exception as exc:
            st.error(f"No se pudo cargar el historial: {exc}")

    st.caption(f"Usuario: {usuario}")

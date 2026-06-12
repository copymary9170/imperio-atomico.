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
    registrar_factura_materia_prima,
)


def _label_item(row: pd.Series) -> str:
    return f"#{int(row['id'])} · {row['nombre']} · stock {float(row['stock_actual'] or 0):g} {row['unidad']} · costo ${float(row['costo_unitario_usd'] or 0):,.4f}"


def render_materia_prima(usuario: str) -> None:
    st.subheader("📦 Materia prima")
    st.caption(
        "Aquí se registran insumos comprados para producir. Para facturas con varios productos usa Compra múltiple: "
        "el delivery, impuesto, comisión, descuento y promoción se reparten proporcionalmente por subtotal."
    )

    tab_existencias, tab_crear, tab_compra, tab_factura, tab_historial = st.tabs([
        "Existencias",
        "Crear materia prima",
        "Compra individual",
        "Compra múltiple / factura",
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
            unidad = i1.selectbox("Unidad de inventario", UNIDADES_MATERIA_PRIMA)
            stock_minimo = i2.number_input("Stock mínimo", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            stock_maximo = i3.number_input("Stock máximo", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            precio_venta = i4.number_input("Precio venta opcional USD", min_value=0.0, value=0.0, step=0.01, format="%.4f")
            st.markdown("###### Unidad técnica para costeo / merma")
            t1, t2, t3 = st.columns(3)
            unidad_tecnica = t1.selectbox("Unidad técnica", UNIDADES_TECNICAS)
            contenido_tecnico = t2.number_input("Contenido técnico por unidad", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            rendimiento_estimado = t3.number_input("Rendimiento estimado", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            compatible_con = st.text_area("Compatible con / notas técnicas")
            submitted = st.form_submit_button("Crear materia prima", use_container_width=True)
        if submitted:
            try:
                item_id = crear_materia_prima(usuario=usuario, sku=sku, nombre=nombre, categoria=categoria, unidad=unidad, stock_minimo=float(stock_minimo), precio_venta_usd=float(precio_venta), proveedor_principal=proveedor_principal, proveedor_alternativo=proveedor_alternativo, marca=marca, fabricante=fabricante, codigo_fabricante=codigo_fabricante, ubicacion=ubicacion, stock_maximo=float(stock_maximo), unidad_tecnica=unidad_tecnica, contenido_tecnico=float(contenido_tecnico), rendimiento_estimado=float(rendimiento_estimado), compatible_con=compatible_con)
                st.success(f"Materia prima creada con ID #{item_id}.")
                st.rerun()
            except Exception as exc:
                st.error(f"No se pudo crear la materia prima: {exc}")

    with tab_compra:
        st.markdown("##### Registrar compra individual con costo real")
        df = listar_materia_prima()
        if df.empty:
            st.warning("Primero crea una materia prima.")
        else:
            opciones = {_label_item(row): int(row["id"]) for _, row in df.iterrows()}
            item_label = st.selectbox("Materia prima", list(opciones.keys()), key="compra_individual_item")
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
                    previo = calcular_costo_real_compra(costo_base_usd=float(costo_base) + float(otros_gastos), cantidad=float(cantidad), impuestos_pct=float(impuestos_pct), delivery_usd=float(delivery), comision_pago_usd=float(comision))
                    p1, p2, p3, p4 = st.columns(4)
                    p1.metric("Total real", f"${previo.total_real_usd:,.4f}")
                    p2.metric("Costo unitario real", f"${previo.costo_unitario_real_usd:,.6f}")
                    p3.metric("Impuesto USD", f"${previo.impuesto_usd:,.4f}")
                    p4.metric("Delivery + comisión + otros", f"${(previo.delivery_usd + previo.comision_pago_usd + float(otros_gastos)):,.4f}")
                submitted = st.form_submit_button("Registrar compra y actualizar stock", use_container_width=True)
            if submitted:
                try:
                    resultado = registrar_compra_materia_prima(usuario=usuario, inventario_id=int(item_id), cantidad_comprada=float(cantidad), costo_base_usd=float(costo_base), impuestos_pct=float(impuestos_pct), delivery_usd=float(delivery), comision_pago_usd=float(comision), moneda_pago=moneda, tasa_cambio=float(tasa), metodo_pago=metodo_pago, tipo_pago=tipo_pago, monto_pagado_inicial_usd=float(monto_inicial) if float(monto_inicial) > 0 else None, referencia=referencia, proveedor=proveedor, factura=factura, otros_gastos_usd=float(otros_gastos))
                    st.success(f"Compra #{resultado['compra_id']} registrada. Stock: {resultado['stock_anterior']} + {resultado['cantidad_comprada']} = {resultado['stock_nuevo']}.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"No se pudo registrar la compra: {exc}")

    with tab_factura:
        st.markdown("##### Registrar factura con varios productos")
        df = listar_materia_prima()
        if df.empty:
            st.warning("Primero crea materia prima.")
        else:
            if "factura_mp_lineas" not in st.session_state:
                st.session_state["factura_mp_lineas"] = []
            opciones = {_label_item(row): int(row["id"]) for _, row in df.iterrows()}
            st.markdown("###### Agregar línea")
            l1, l2, l3 = st.columns([3, 1, 1])
            linea_label = l1.selectbox("Materia prima", list(opciones.keys()), key="factura_linea_item")
            linea_cantidad = l2.number_input("Cantidad", min_value=0.0001, value=1.0, step=1.0, format="%.4f", key="factura_linea_cantidad")
            linea_subtotal = l3.number_input("Subtotal línea USD", min_value=0.0, value=0.0, step=1.0, format="%.4f", key="factura_linea_subtotal")
            if st.button("➕ Agregar línea a factura", use_container_width=True):
                st.session_state["factura_mp_lineas"].append({"inventario_id": opciones[linea_label], "item": linea_label, "cantidad": float(linea_cantidad), "subtotal_usd": float(linea_subtotal)})
                st.success("Línea agregada.")
            lineas = st.session_state.get("factura_mp_lineas", [])
            if lineas:
                st.dataframe(pd.DataFrame(lineas), use_container_width=True, hide_index=True)
                if st.button("🧹 Limpiar líneas", use_container_width=True):
                    st.session_state["factura_mp_lineas"] = []
                    st.rerun()
            subtotal = sum(float(x.get("subtotal_usd") or 0) for x in lineas)
            st.markdown("###### Datos generales de factura")
            with st.form("form_factura_materia_prima"):
                f1, f2, f3 = st.columns(3)
                proveedor_factura = f1.text_input("Proveedor")
                numero_factura = f2.text_input("Número de factura")
                referencia_factura = f3.text_input("Referencia / nota")
                g1, g2, g3, g4, g5 = st.columns(5)
                descuento = g1.number_input("Descuento / promo USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                impuestos_factura = g2.number_input("Impuestos %", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                delivery_total = g3.number_input("Delivery total USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                comision_total = g4.number_input("Comisión total USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")
                otros_total = g5.number_input("Otros gastos USD", min_value=0.0, value=0.0, step=0.5, format="%.4f")
                p1, p2, p3, p4 = st.columns(4)
                moneda_factura = p1.selectbox("Moneda", ["USD", "Bs", "COP", "EUR"], key="factura_moneda")
                tasa_factura = p2.number_input("Tasa", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
                metodo_factura = p3.selectbox("Método de pago", ["efectivo", "transferencia", "pago movil", "binance", "zelle", "punto", "otro"], key="factura_metodo")
                tipo_factura = p4.selectbox("Tipo de pago", ["contado", "credito", "parcial"], key="factura_tipo")
                monto_inicial_factura = st.number_input("Monto pagado inicial USD", min_value=0.0, value=0.0, step=1.0, format="%.4f", key="factura_monto_inicial")
                base_desc = max(0.0, subtotal - float(descuento)) + float(otros_total)
                impuesto_total = base_desc * (float(impuestos_factura) / 100.0)
                total_factura = base_desc + impuesto_total + float(delivery_total) + float(comision_total)
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Subtotal líneas", f"${subtotal:,.4f}")
                m2.metric("Base con descuento", f"${base_desc:,.4f}")
                m3.metric("Impuesto total", f"${impuesto_total:,.4f}")
                m4.metric("Total factura", f"${total_factura:,.4f}")
                submitted_factura = st.form_submit_button("Registrar factura completa", use_container_width=True, disabled=not bool(lineas))
            if submitted_factura:
                try:
                    resultado = registrar_factura_materia_prima(usuario=usuario, proveedor=proveedor_factura, factura=numero_factura, lineas=lineas, delivery_total_usd=float(delivery_total), impuestos_pct=float(impuestos_factura), comision_total_usd=float(comision_total), descuento_total_usd=float(descuento), otros_gastos_usd=float(otros_total), moneda_pago=moneda_factura, tasa_cambio=float(tasa_factura), metodo_pago=metodo_factura, tipo_pago=tipo_factura, monto_pagado_inicial_usd=float(monto_inicial_factura) if float(monto_inicial_factura) > 0 else None, referencia=referencia_factura)
                    st.session_state["factura_mp_lineas"] = []
                    st.success(f"Factura registrada. Total: ${resultado['total_factura_usd']:,.4f}. Líneas: {len(resultado['lineas'])}.")
                    st.dataframe(pd.DataFrame(resultado["lineas"]), use_container_width=True, hide_index=True)
                except Exception as exc:
                    st.error(f"No se pudo registrar la factura: {exc}")

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

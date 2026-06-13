from __future__ import annotations

import pandas as pd
import streamlit as st

from services.reventa_service import (
    CATEGORIAS_REVENTA,
    UNIDADES_REVENTA,
    crear_mercancia_reventa,
    listar_compras_reventa,
    listar_mercancia_reventa,
    registrar_compra_reventa,
)


def _label_item(row: pd.Series) -> str:
    return f"#{int(row['id'])} · {row['nombre']} · stock {float(row['stock_actual'] or 0):g} {row['unidad']}"


def render_mercancia_reventa(usuario: str) -> None:
    st.subheader("🛍️ Mercancía para reventa")
    st.caption("Productos que compras para vender sin transformarlos: lápices, borradores, carpetas, colores, grapas, sacapuntas, etc.")

    tab_stock, tab_crear, tab_compra, tab_historial = st.tabs(["Stock", "Crear producto", "Registrar compra", "Historial"])

    with tab_stock:
        df = listar_mercancia_reventa()
        if df.empty:
            st.info("Aún no hay mercancía para reventa.")
        else:
            st.dataframe(df, use_container_width=True, hide_index=True)

    with tab_crear:
        with st.form("form_crear_reventa"):
            c1, c2, c3 = st.columns(3)
            sku = c1.text_input("SKU")
            nombre = c2.text_input("Nombre")
            categoria = c3.selectbox("Categoría", CATEGORIAS_REVENTA)
            c4, c5, c6 = st.columns(3)
            marca = c4.text_input("Marca")
            proveedor = c5.text_input("Proveedor principal")
            unidad = c6.selectbox("Unidad", UNIDADES_REVENTA)
            c7, c8, c9 = st.columns(3)
            precio = c7.number_input("Precio venta USD", min_value=0.0, value=0.0, step=0.1, format="%.4f")
            stock_min = c8.number_input("Stock mínimo", min_value=0.0, value=0.0, step=1.0, format="%.4f")
            ubicacion = c9.text_input("Ubicación")
            submitted = st.form_submit_button("Crear mercancía", use_container_width=True)
        if submitted:
            try:
                item_id = crear_mercancia_reventa(usuario=usuario, sku=sku, nombre=nombre, categoria=categoria, unidad=unidad, precio_venta_usd=float(precio), stock_minimo=float(stock_min), marca=marca, proveedor_principal=proveedor, ubicacion=ubicacion)
                st.success(f"Mercancía creada: #{item_id}")
            except Exception as exc:
                st.error(f"No se pudo crear: {exc}")

    with tab_compra:
        df = listar_mercancia_reventa()
        if df.empty:
            st.warning("Primero crea mercancía para reventa.")
        else:
            opciones = {_label_item(row): int(row["id"]) for _, row in df.iterrows()}
            with st.form("form_compra_reventa"):
                item_label = st.selectbox("Mercancía", list(opciones.keys()))
                c1, c2, c3 = st.columns(3)
                cantidad = c1.number_input("Cantidad comprada", min_value=0.0001, value=1.0, step=1.0, format="%.4f")
                costo_total = c2.number_input("Costo total USD", min_value=0.0, value=0.0, step=1.0, format="%.4f")
                precio_venta = c3.number_input("Nuevo precio venta USD opcional", min_value=0.0, value=0.0, step=0.1, format="%.4f")
                c4, c5, c6 = st.columns(3)
                proveedor = c4.text_input("Proveedor")
                factura = c5.text_input("Factura")
                referencia = c6.text_input("Referencia")
                total_unit = costo_total / cantidad if cantidad else 0
                st.metric("Costo unitario compra", f"${total_unit:,.4f}")
                submitted = st.form_submit_button("Registrar compra", use_container_width=True)
            if submitted:
                try:
                    res = registrar_compra_reventa(usuario=usuario, mercancia_id=opciones[item_label], cantidad=float(cantidad), costo_total_usd=float(costo_total), precio_venta_usd=float(precio_venta) if float(precio_venta) > 0 else None, proveedor=proveedor, factura=factura, referencia=referencia)
                    st.success(f"Compra registrada. Stock nuevo: {res['stock_nuevo']:,.4f}. Costo promedio: ${res['costo_promedio_usd']:,.4f}.")
                except Exception as exc:
                    st.error(f"No se pudo registrar: {exc}")

    with tab_historial:
        compras = listar_compras_reventa(limit=100)
        if compras.empty:
            st.info("Aún no hay compras de reventa.")
        else:
            st.dataframe(compras, use_container_width=True, hide_index=True)

    st.caption(f"Usuario: {usuario}")

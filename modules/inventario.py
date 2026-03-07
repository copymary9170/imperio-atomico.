from __future__ import annotations

import streamlit as st

from database.connection import db_transaction


def create_producto(usuario: str, sku: str, nombre: str, categoria: str, unidad: str, costo: float, precio: float) -> int:
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO inventario (usuario, sku, nombre, categoria, unidad, costo_unitario_usd, precio_venta_usd)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, sku, nombre, categoria, unidad, costo, precio),
        )
        return int(cur.lastrowid)


def add_inventory_movement(usuario: str, inventario_id: int, tipo: str, cantidad: float, costo_unitario_usd: float, referencia: str) -> None:
    sign = 1 if tipo == "entrada" else -1
    with db_transaction() as conn:
        conn.execute(
            """
            INSERT INTO movimientos_inventario (usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (usuario, inventario_id, tipo, cantidad, costo_unitario_usd, referencia),
        )
        conn.execute(
            "UPDATE inventario SET stock_actual = stock_actual + ? WHERE id = ?",
            (sign * cantidad, inventario_id),
        )


def render_inventario(usuario: str) -> None:
    st.subheader("Inventario")
    with st.form("crear_producto"):
        sku = st.text_input("SKU")
        nombre = st.text_input("Producto")
        categoria = st.text_input("Categoría", value="Papelería")
        unidad = st.text_input("Unidad", value="unidad")
        costo = st.number_input("Costo USD", min_value=0.0)
        precio = st.number_input("Precio USD", min_value=0.0)
        save = st.form_submit_button("Crear producto")
    if save:
        pid = create_producto(usuario, sku, nombre, categoria, unidad, costo, precio)
        st.success(f"Producto #{pid} creado")

    with db_transaction() as conn:
        rows = conn.execute(
            "SELECT id, sku, nombre, categoria, stock_actual, costo_unitario_usd, precio_venta_usd FROM inventario WHERE estado='activo'"
        ).fetchall()
    st.dataframe(rows, use_container_width=True)

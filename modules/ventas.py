from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from utils.currency import convert_to_bs


def registrar_venta(
    usuario: str,
    cliente_id: int | None,
    moneda: str,
    tasa_cambio: float,
    metodo_pago: str,
    items: list[dict],
) -> int:
    subtotal = round(sum(item["cantidad"] * item["precio_unitario_usd"] for item in items), 2)
    impuesto = 0.0
    total = subtotal + impuesto
    total_bs = convert_to_bs(total, tasa_cambio)

    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO ventas (usuario, cliente_id, moneda, tasa_cambio, metodo_pago, subtotal_usd, impuesto_usd, total_usd, total_bs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, cliente_id, moneda, tasa_cambio, metodo_pago, subtotal, impuesto, total, total_bs),
        )
        venta_id = int(cur.lastrowid)

        for item in items:
            conn.execute(
                """
                INSERT INTO ventas_detalle (usuario, venta_id, inventario_id, descripcion, cantidad, precio_unitario_usd, costo_unitario_usd, subtotal_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    venta_id,
                    item.get("inventario_id"),
                    item["descripcion"],
                    item["cantidad"],
                    item["precio_unitario_usd"],
                    item["costo_unitario_usd"],
                    round(item["cantidad"] * item["precio_unitario_usd"], 2),
                ),
            )
            if item.get("inventario_id"):
                conn.execute(
                    "UPDATE inventario SET stock_actual = stock_actual - ? WHERE id = ?",
                    (item["cantidad"], item["inventario_id"]),
                )

        if metodo_pago == "credito" and cliente_id:
            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar (usuario, cliente_id, venta_id, saldo_usd, estado)
                VALUES (?, ?, ?, ?, 'pendiente')
                """,
                (usuario, cliente_id, venta_id, total),
            )

        return venta_id


def render_ventas(usuario: str) -> None:
    st.subheader("Ventas")
    with db_transaction() as conn:
        products = conn.execute("SELECT id, nombre, precio_venta_usd, costo_unitario_usd FROM inventario WHERE estado='activo'").fetchall()

    selected = st.selectbox("Producto", products, format_func=lambda r: f"{r['id']} - {r['nombre']}") if products else None
    cantidad = st.number_input("Cantidad", min_value=1.0, value=1.0)
    metodo_pago = st.selectbox("Método pago", ["efectivo", "transferencia", "zelle", "binance", "credito"])
    moneda = st.selectbox("Moneda", ["USD", "BS", "USDT", "KONTIGO"])
    tasa = st.number_input("Tasa BCV", min_value=0.0001, value=36.5)

    if st.button("Registrar venta") and selected:
        items = [{
            "inventario_id": selected["id"],
            "descripcion": selected["nombre"],
            "cantidad": cantidad,
            "precio_unitario_usd": selected["precio_venta_usd"],
            "costo_unitario_usd": selected["costo_unitario_usd"],
        }]
        vid = registrar_venta(usuario, None, moneda, tasa, metodo_pago, items)
        st.success(f"Venta #{vid} registrada")

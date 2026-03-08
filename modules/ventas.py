from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from modules.common import as_positive, clean_text
from utils.currency import convert_to_bs


# ============================================================
# REGISTRAR VENTA
# ============================================================

def registrar_venta(
    usuario: str,
    cliente_id: int | None,
    moneda: str,
    tasa_cambio: float,
    metodo_pago: str,
    items: list[dict],
) -> int:

    if not items:
        raise ValueError("Debe agregar al menos un item")

    tasa_cambio = as_positive(
        tasa_cambio,
        "Tasa de cambio",
        allow_zero=False
    )

    subtotal = round(
        sum(
            as_positive(item["cantidad"], "Cantidad", allow_zero=False)
            * as_positive(item["precio_unitario_usd"], "Precio")
            for item in items
        ),
        2
    )

    impuesto = 0.0
    total = subtotal + impuesto

    total_bs = convert_to_bs(total, tasa_cambio)

    with db_transaction() as conn:

        cur = conn.execute(
            """
            INSERT INTO ventas
            (usuario, cliente_id, moneda, tasa_cambio, metodo_pago,
             subtotal_usd, impuesto_usd, total_usd, total_bs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                cliente_id,
                moneda,
                tasa_cambio,
                metodo_pago,
                subtotal,
                impuesto,
                total,
                total_bs
            ),
        )

        venta_id = int(cur.lastrowid)

        # -----------------------------------
        # DETALLE VENTA
        # -----------------------------------

        for item in items:

            cantidad = as_positive(item["cantidad"], "Cantidad", allow_zero=False)

            precio_u = as_positive(item["precio_unitario_usd"], "Precio unitario")

            costo_u = as_positive(item["costo_unitario_usd"], "Costo unitario")

            descripcion = clean_text(item.get("descripcion")) or "Item"

            inventario_id = item.get("inventario_id")

            conn.execute(
                """
                INSERT INTO ventas_detalle
                (usuario, venta_id, inventario_id, descripcion,
                 cantidad, precio_unitario_usd, costo_unitario_usd, subtotal_usd)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usuario,
                    venta_id,
                    inventario_id,
                    descripcion,
                    cantidad,
                    precio_u,
                    costo_u,
                    round(cantidad * precio_u, 2),
                ),
            )

            # -----------------------------------
            # DESCONTAR INVENTARIO
            # -----------------------------------

            if inventario_id:

                current = conn.execute(
                    """
                    SELECT stock_actual
                    FROM inventario
                    WHERE id=? AND estado='activo'
                    """,
                    (inventario_id,),
                ).fetchone()

                if not current:
                    raise ValueError(f"Inventario #{inventario_id} no existe")

                if float(current["stock_actual"] or 0.0) < cantidad:
                    raise ValueError("Stock insuficiente")

                conn.execute(
                    """
                    UPDATE inventario
                    SET stock_actual = stock_actual - ?
                    WHERE id = ?
                    """,
                    (cantidad, inventario_id),
                )

        # -----------------------------------
        # CUENTAS POR COBRAR
        # -----------------------------------

        if metodo_pago == "credito" and cliente_id:

            conn.execute(
                """
                INSERT INTO cuentas_por_cobrar
                (usuario, cliente_id, venta_id, saldo_usd, estado)
                VALUES (?, ?, ?, ?, 'pendiente')
                """,
                (
                    usuario,
                    cliente_id,
                    venta_id,
                    total
                ),
            )

        return venta_id


# ============================================================
# INTERFAZ VENTAS
# ============================================================

def render_ventas(usuario: str) -> None:

    st.subheader("💰 Ventas")

    try:

        with db_transaction() as conn:

            products = conn.execute(
                """
                SELECT
                id,
                nombre,
                precio_venta_usd,
                costo_unitario_usd,
                stock_actual
                FROM inventario
                WHERE estado='activo'
                """
            ).fetchall()

            resumen = conn.execute(
                """
                SELECT
                    COALESCE(SUM(total_usd),0) AS total,
                    COALESCE(
                        SUM(
                            CASE
                            WHEN date(fecha)=date('now')
                            THEN total_usd
                            ELSE 0
                            END
                        ),
                    0) AS hoy,
                    COUNT(*) AS cantidad
                FROM ventas
                WHERE estado='registrada'
                """
            ).fetchone()

    except Exception as e:

        st.error("Error cargando ventas")

        st.exception(e)

        return

    # ------------------------------------------------
    # SELECCIÓN PRODUCTO
    # ------------------------------------------------

    selected = None

    if products:

        selected = st.selectbox(
            "Producto",
            products,
            format_func=lambda r: f"{r['id']} - {r['nombre']} (Stock: {float(r['stock_actual']):,.2f})"
        )

    cantidad = st.number_input(
        "Cantidad",
        min_value=1.0,
        value=1.0
    )

    metodo_pago = st.selectbox(
        "Método pago",
        ["efectivo", "transferencia", "zelle", "binance", "credito"]
    )

    moneda = st.selectbox(
        "Moneda",
        ["USD", "BS", "USDT", "KONTIGO"]
    )

    tasa = st.number_input(
        "Tasa BCV",
        min_value=0.0001,
        value=36.5
    )

    # ------------------------------------------------
    # REGISTRAR VENTA
    # ------------------------------------------------

    if st.button("💾 Registrar venta") and selected:

        items = [{
            "inventario_id": selected["id"],
            "descripcion": selected["nombre"],
            "cantidad": cantidad,
            "precio_unitario_usd": selected["precio_venta_usd"],
            "costo_unitario_usd": selected["costo_unitario_usd"],
        }]

        try:

            vid = registrar_venta(
                usuario,
                None,
                moneda,
                tasa,
                metodo_pago,
                items
            )

            st.success(f"Venta #{vid} registrada")

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

    st.divider()

    # ------------------------------------------------
    # MÉTRICAS
    # ------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Ventas registradas",
        int(resumen["cantidad"] or 0)
    )

    c2.metric(
        "Ventas de hoy",
        f"$ {float(resumen['hoy'] or 0):,.2f}"
    )

    c3.metric(
        "Ventas acumuladas",
        f"$ {float(resumen['total'] or 0):,.2f}"
    )

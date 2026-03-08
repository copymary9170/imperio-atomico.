from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from modules.common import as_positive, clean_text, money, require_text


# ============================================================
# CREAR PRODUCTO
# ============================================================

def create_producto(
    usuario: str,
    sku: str,
    nombre: str,
    categoria: str,
    unidad: str,
    costo: float,
    precio: float
) -> int:

    sku = require_text(sku, "SKU")
    nombre = require_text(nombre, "Producto")
    categoria = require_text(categoria, "Categoría")
    unidad = require_text(unidad, "Unidad")

    costo = as_positive(costo, "Costo")
    precio = as_positive(precio, "Precio")

    with db_transaction() as conn:

        cur = conn.execute(
            """
            INSERT INTO inventario (
                usuario,
                sku,
                nombre,
                categoria,
                unidad,
                costo_unitario_usd,
                precio_venta_usd
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                sku,
                nombre,
                categoria,
                unidad,
                money(costo),
                money(precio)
            ),
        )

        return int(cur.lastrowid)


# ============================================================
# MOVIMIENTOS INVENTARIO
# ============================================================

def add_inventory_movement(
    usuario: str,
    inventario_id: int,
    tipo: str,
    cantidad: float,
    costo_unitario_usd: float,
    referencia: str
) -> None:

    if tipo not in {"entrada", "salida", "ajuste"}:
        raise ValueError("Tipo de movimiento inválido")

    cantidad = as_positive(
        cantidad,
        "Cantidad",
        allow_zero=False
    )

    costo_unitario_usd = as_positive(
        costo_unitario_usd,
        "Costo unitario"
    )

    referencia = clean_text(referencia)

    sign = 1 if tipo == "entrada" else -1

    with db_transaction() as conn:

        current = conn.execute(
            """
            SELECT stock_actual
            FROM inventario
            WHERE id=? AND estado='activo'
            """,
            (inventario_id,)
        ).fetchone()

        if not current:
            raise ValueError("Producto no existe o está inactivo")

        resulting_stock = float(current["stock_actual"] or 0.0) + (sign * cantidad)

        if resulting_stock < 0:
            raise ValueError("Stock insuficiente para registrar salida")

        conn.execute(
            """
            INSERT INTO movimientos_inventario (
                usuario,
                inventario_id,
                tipo,
                cantidad,
                costo_unitario_usd,
                referencia
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                inventario_id,
                tipo,
                cantidad,
                money(costo_unitario_usd),
                referencia,
            ),
        )

        conn.execute(
            """
            UPDATE inventario
            SET stock_actual = stock_actual + ?
            WHERE id = ?
            """,
            (sign * cantidad, inventario_id),
        )


# ============================================================
# INTERFAZ INVENTARIO
# ============================================================

def render_inventario(usuario: str) -> None:

    st.subheader("📦 Inventario")

    # ------------------------------------------------
    # CREAR PRODUCTO
    # ------------------------------------------------

    with st.form("crear_producto"):

        st.write("Registrar nuevo producto")

        c1, c2 = st.columns(2)

        sku = c1.text_input("SKU")

        nombre = c1.text_input("Producto")

        categoria = c2.text_input(
            "Categoría",
            value="Papelería"
        )

        unidad = c2.text_input(
            "Unidad",
            value="unidad"
        )

        costo = st.number_input(
            "Costo USD",
            min_value=0.0
        )

        precio = st.number_input(
            "Precio USD",
            min_value=0.0
        )

        save = st.form_submit_button("💾 Crear producto")

    if save:

        try:

            pid = create_producto(
                usuario,
                sku,
                nombre,
                categoria,
                unidad,
                costo,
                precio
            )

            st.success(f"Producto #{pid} creado")

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

        except Exception as e:

            st.error("Error creando producto")

            st.exception(e)

    st.divider()

    # ------------------------------------------------
    # RESUMEN INVENTARIO
    # ------------------------------------------------

    try:

        with db_transaction() as conn:

            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COALESCE(SUM(stock_actual),0) AS stock,
                    COALESCE(SUM(stock_actual * costo_unitario_usd),0) AS valor_stock
                FROM inventario
                WHERE estado='activo'
                """
            ).fetchone()

            rows = conn.execute(
                """
                SELECT
                    id,
                    sku,
                    nombre,
                    categoria,
                    stock_actual,
                    costo_unitario_usd,
                    precio_venta_usd
                FROM inventario
                WHERE estado='activo'
                ORDER BY id DESC
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando inventario")

        st.exception(e)

        return

    # ------------------------------------------------
    # MÉTRICAS
    # ------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Productos activos",
        int(totals["total"] or 0)
    )

    c2.metric(
        "Stock total",
        f"{float(totals['stock'] or 0):,.2f}"
    )

    c3.metric(
        "Valor inventario",
        f"$ {float(totals['valor_stock'] or 0):,.2f}"
    )

    st.divider()

    # ------------------------------------------------
    # TABLA INVENTARIO
    # ------------------------------------------------

    if not rows:

        st.info("No hay productos registrados.")

        return

    df = pd.DataFrame(rows)

    buscar = st.text_input("🔎 Buscar producto")

    if buscar:

        df = df[
            df["nombre"]
            .str.contains(buscar, case=False, na=False)
        ]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

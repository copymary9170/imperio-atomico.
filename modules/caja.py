from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text


# ============================================================
# 🏦 REGISTRAR CIERRE DE CAJA
# ============================================================

def registrar_cierre_caja(
    usuario: str,
    cash_start: float,
    sales_cash: float,
    sales_transfer: float,
    sales_zelle: float,
    sales_binance: float,
    expenses_cash: float,
    expenses_transfer: float,
    observaciones: str,
) -> int:
    """
    Registra un cierre de caja en la base de datos.
    """

    # Validaciones
    cash_start = as_positive(cash_start, "Caja inicial")
    sales_cash = as_positive(sales_cash, "Ventas efectivo")
    sales_transfer = as_positive(sales_transfer, "Ventas transferencia")
    sales_zelle = as_positive(sales_zelle, "Ventas Zelle")
    sales_binance = as_positive(sales_binance, "Ventas Binance")
    expenses_cash = as_positive(expenses_cash, "Egresos efectivo")
    expenses_transfer = as_positive(expenses_transfer, "Egresos transferencia")

    observaciones = clean_text(observaciones)

    # Cálculo final de caja
    cash_end = cash_start + sales_cash - expenses_cash

    with db_transaction() as conn:

        cur = conn.execute(
            """
            INSERT INTO cierres_caja (
                usuario,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_zelle,
                sales_binance,
                expenses_cash,
                expenses_transfer,
                cash_end,
                observaciones
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_zelle,
                sales_binance,
                expenses_cash,
                expenses_transfer,
                cash_end,
                observaciones,
            ),
        )

        return int(cur.lastrowid)


# ============================================================
# 💰 INTERFAZ DE CIERRE DE CAJA
# ============================================================

def render_caja(usuario: str, user_role: str) -> None:

    st.subheader("🏦 Cierre de Caja")

    # Seguridad
    if user_role != "Admin":
        st.warning("Solo usuarios Admin pueden realizar cierres de caja.")
        return

    # Mostrar último cierre
    try:

        with db_transaction() as conn:

            ultimo = conn.execute(
                """
                SELECT fecha, cash_start, cash_end
                FROM cierres_caja
                ORDER BY id DESC
                LIMIT 1
                """
            ).fetchone()

    except Exception:
        ultimo = None

    if ultimo:

        st.info(
            f"""
Último cierre

Fecha: {ultimo['fecha']}

Inicio: $ {float(ultimo['cash_start']):,.2f}

Final: $ {float(ultimo['cash_end']):,.2f}
"""
        )

    st.divider()

    st.subheader("Datos del día")

    c1, c2 = st.columns(2)

    with c1:

        cash_start = st.number_input(
            "Caja inicial ($)",
            min_value=0.0,
            step=1.0
        )

        sales_cash = st.number_input(
            "Ventas en efectivo ($)",
            min_value=0.0,
            step=1.0
        )

        sales_transfer = st.number_input(
            "Ventas por transferencia ($)",
            min_value=0.0,
            step=1.0
        )

        sales_zelle = st.number_input(
            "Ventas por Zelle ($)",
            min_value=0.0,
            step=1.0
        )

    with c2:

        sales_binance = st.number_input(
            "Ventas por Binance ($)",
            min_value=0.0,
            step=1.0
        )

        expenses_cash = st.number_input(
            "Egresos en efectivo ($)",
            min_value=0.0,
            step=1.0
        )

        expenses_transfer = st.number_input(
            "Egresos por transferencia ($)",
            min_value=0.0,
            step=1.0
        )

    observaciones = st.text_area(
        "Observaciones del cierre"
    )

    st.divider()

    # Cálculo en tiempo real
    cash_end_preview = cash_start + sales_cash - expenses_cash

    m1, m2 = st.columns(2)

    m1.metric(
        "Caja inicial",
        f"$ {cash_start:,.2f}"
    )

    m2.metric(
        "Caja final estimada",
        f"$ {cash_end_preview:,.2f}"
    )

    st.divider()

    # Botón de cierre
    if st.button("💾 Registrar cierre de caja"):

        try:

            cierre_id = registrar_cierre_caja(
                usuario,
                cash_start,
                sales_cash,
                sales_transfer,
                sales_zelle,
                sales_binance,
                expenses_cash,
                expenses_transfer,
                observaciones,
            )

            st.success(f"Cierre de caja #{cierre_id} registrado correctamente")

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

        except Exception as e:

            st.error("Error registrando cierre de caja")

            st.exception(e)

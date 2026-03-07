from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from modules.common import as_positive, clean_text


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
    cash_start = as_positive(cash_start, "Caja inicial")
    sales_cash = as_positive(sales_cash, "Ventas efectivo")
    sales_transfer = as_positive(sales_transfer, "Ventas transferencia")
    sales_zelle = as_positive(sales_zelle, "Ventas zelle")
    sales_binance = as_positive(sales_binance, "Ventas binance")
    expenses_cash = as_positive(expenses_cash, "Egresos efectivo")
    expenses_transfer = as_positive(expenses_transfer, "Egresos transferencia")
    observaciones = clean_text(observaciones)

    cash_end = cash_start + sales_cash - expenses_cash
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO cierres_caja (
                usuario, cash_start, sales_cash, sales_transfer, sales_zelle, sales_binance,
                expenses_cash, expenses_transfer, cash_end, observaciones
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


def render_caja(usuario: str, user_role: str) -> None:
    st.subheader("Cierre de Caja")
    if user_role != "Admin":
        st.warning("Solo Admin puede cerrar caja.")
        return

    with db_transaction() as conn:
        ultimo = conn.execute(
            "SELECT fecha, cash_start, cash_end FROM cierres_caja ORDER BY id DESC LIMIT 1"
        ).fetchone()

    if ultimo:
        st.info(
            f"Último cierre: {ultimo['fecha']} | Inicio: $ {float(ultimo['cash_start']):,.2f} | Final: $ {float(ultimo['cash_end']):,.2f}"
        )

    cash_start = st.number_input("cash_start", min_value=0.0)
    sales_cash = st.number_input("sales_cash", min_value=0.0)
    sales_transfer = st.number_input("sales_transfer", min_value=0.0)
    sales_zelle = st.number_input("sales_zelle", min_value=0.0)
    sales_binance = st.number_input("sales_binance", min_value=0.0)
    expenses_cash = st.number_input("expenses_cash", min_value=0.0)
    expenses_transfer = st.number_input("expenses_transfer", min_value=0.0)
    observaciones = st.text_area("Observaciones")

    if st.button("Cerrar caja"):
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
            st.success(f"Cierre #{cierre_id} registrado")
        except ValueError as exc:
            st.error(str(exc))

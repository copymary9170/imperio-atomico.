from __future__ import annotations

import streamlit as st

from database.connection import db_transaction
from utils.currency import convert_to_bs, convert_to_usd


def registrar_gasto(
    usuario: str,
    descripcion: str,
    categoria: str,
    metodo_pago: str,
    moneda: str,
    tasa_cambio: float,
    monto: float,
) -> int:
    monto_usd = convert_to_usd(monto, moneda, tasa_cambio)
    monto_bs = convert_to_bs(monto_usd, tasa_cambio)
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO gastos (usuario, descripcion, categoria, metodo_pago, moneda, tasa_cambio, monto_usd, monto_bs)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (usuario, descripcion, categoria, metodo_pago, moneda, tasa_cambio, monto_usd, monto_bs),
        )
        return int(cur.lastrowid)


def cancelar_gasto(gasto_id: int, motivo: str) -> None:
    with db_transaction() as conn:
        conn.execute(
            "UPDATE gastos SET estado='cancelado', cancelado_motivo=? WHERE id=? AND estado='activo'",
            (motivo, gasto_id),
        )


def render_gastos(usuario: str) -> None:
    st.subheader("Gastos")
    with st.form("nuevo_gasto"):
        descripcion = st.text_input("Descripción")
        categoria = st.selectbox("Categoría", ["Operativo", "Nómina", "Servicios", "Materia Prima", "Marketing"])
        metodo = st.selectbox("Método de pago", ["efectivo", "transferencia", "pago móvil", "binance", "kontigo"])
        moneda = st.selectbox("Moneda", ["USD", "BS", "USDT", "KONTIGO"])
        tasa = st.number_input("Tasa BCV", min_value=0.0001, value=36.5)
        monto = st.number_input("Monto", min_value=0.0)
        submit = st.form_submit_button("Registrar gasto")
    if submit:
        gid = registrar_gasto(usuario, descripcion, categoria, metodo, moneda, tasa, monto)
        st.success(f"Gasto #{gid} registrado")

    with db_transaction() as conn:
        rows = conn.execute(
            "SELECT id, fecha, descripcion, categoria, metodo_pago, monto_usd, estado FROM gastos ORDER BY id DESC"
        ).fetchall()
    st.dataframe(rows, use_container_width=True)

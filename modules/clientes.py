from __future__ import annotations

import streamlit as st

from database.connection import db_transaction


def create_cliente(usuario: str, nombre: str, telefono: str, email: str, direccion: str, limite_credito_usd: float) -> int:
    with db_transaction() as conn:
        cur = conn.execute(
            """
            INSERT INTO clientes (usuario, nombre, telefono, email, direccion, limite_credito_usd)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (usuario, nombre, telefono, email, direccion, limite_credito_usd),
        )
        return int(cur.lastrowid)


def render_clientes(usuario: str) -> None:
    st.subheader("Clientes")
    with st.form("form_cliente"):
        nombre = st.text_input("Nombre")
        telefono = st.text_input("Teléfono")
        email = st.text_input("Email")
        direccion = st.text_area("Dirección")
        limite_credito = st.number_input("Límite crédito USD", min_value=0.0, step=1.0)
        submitted = st.form_submit_button("Guardar cliente")

    if submitted:
        cid = create_cliente(usuario, nombre, telefono, email, direccion, limite_credito)
        st.success(f"Cliente #{cid} registrado")

    with db_transaction() as conn:
        data = conn.execute(
            "SELECT id, fecha, nombre, telefono, saldo_por_cobrar_usd, estado FROM clientes ORDER BY id DESC"
        ).fetchall()
    st.dataframe(data, use_container_width=True)

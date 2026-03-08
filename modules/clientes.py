from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from modules.common import as_positive, clean_text, require_text


# ============================================================
# 👤 CREAR CLIENTE
# ============================================================

def create_cliente(
    usuario: str,
    nombre: str,
    telefono: str,
    email: str,
    direccion: str,
    limite_credito_usd: float
) -> int:

    nombre = require_text(nombre, "Nombre")
    telefono = clean_text(telefono)
    email = clean_text(email)
    direccion = clean_text(direccion)
    limite_credito_usd = as_positive(limite_credito_usd, "Límite de crédito")

    with db_transaction() as conn:

        cur = conn.execute(
            """
            INSERT INTO clientes (
                usuario,
                nombre,
                telefono,
                email,
                direccion,
                limite_credito_usd
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                usuario,
                nombre,
                telefono,
                email,
                direccion,
                limite_credito_usd,
            ),
        )

        return int(cur.lastrowid)


# ============================================================
# 📊 INTERFAZ CLIENTES
# ============================================================

def render_clientes(usuario: str) -> None:

    st.subheader("👤 Gestión de Clientes")

    # ------------------------------------------------
    # FORMULARIO
    # ------------------------------------------------

    with st.form("form_cliente"):

        st.write("Registrar nuevo cliente")

        c1, c2 = st.columns(2)

        nombre = c1.text_input("Nombre")
        telefono = c1.text_input("Teléfono")

        email = c2.text_input("Email")
        direccion = c2.text_area("Dirección")

        limite_credito = st.number_input(
            "Límite crédito USD",
            min_value=0.0,
            step=1.0
        )

        submitted = st.form_submit_button("💾 Guardar cliente")

    if submitted:

        try:

            cid = create_cliente(
                usuario,
                nombre,
                telefono,
                email,
                direccion,
                limite_credito
            )

            st.success(f"Cliente #{cid} registrado correctamente")

            st.balloons()

        except ValueError as exc:

            st.error(str(exc))

        except Exception as e:

            st.error("Error registrando cliente")

            st.exception(e)

    st.divider()

    # ------------------------------------------------
    # ESTADÍSTICAS
    # ------------------------------------------------

    try:

        with db_transaction() as conn:

            totals = conn.execute(
                """
                SELECT
                    COUNT(*) AS total_clientes,
                    COALESCE(SUM(saldo_por_cobrar_usd), 0) AS saldo_total,
                    COALESCE(AVG(limite_credito_usd), 0) AS limite_promedio
                FROM clientes
                WHERE estado='activo'
                """
            ).fetchone()

            rows = conn.execute(
                """
                SELECT
                    id,
                    fecha,
                    nombre,
                    telefono,
                    saldo_por_cobrar_usd,
                    estado
                FROM clientes
                ORDER BY id DESC
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando clientes")

        st.exception(e)

        return

    # ------------------------------------------------
    # MÉTRICAS
    # ------------------------------------------------

    c1, c2, c3 = st.columns(3)

    c1.metric(
        "Clientes activos",
        int(totals["total_clientes"] or 0)
    )

    c2.metric(
        "Saldo por cobrar",
        f"$ {float(totals['saldo_total'] or 0):,.2f}"
    )

    c3.metric(
        "Límite promedio",
        f"$ {float(totals['limite_promedio'] or 0):,.2f}"
    )

    st.divider()

    # ------------------------------------------------
    # TABLA CLIENTES
    # ------------------------------------------------

    if not rows:

        st.info("No hay clientes registrados.")

        return

    df = pd.DataFrame(rows)

    buscador = st.text_input("🔎 Buscar cliente")

    if buscador:

        df = df[
            df["nombre"].str.contains(buscador, case=False, na=False)
        ]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

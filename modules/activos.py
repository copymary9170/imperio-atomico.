from __future__ import annotations

import streamlit as st
import pandas as pd

from database.connection import db_transaction
from modules.common import require_text, as_positive


# =========================================================
# CREAR ACTIVO
# =========================================================

def crear_activo(
    usuario: str,
    equipo: str,
    modelo: str,
    categoria: str,
    costo_hora: float
) -> int:

    equipo = require_text(equipo, "Equipo")
    modelo = require_text(modelo, "Modelo")
    categoria = require_text(categoria, "Categoría")
    costo_hora = as_positive(costo_hora, "Costo hora")

    with db_transaction() as conn:

        cur = conn.execute(
            """
            INSERT INTO activos (
                equipo,
                modelo,
                categoria,
                costo_hora,
                activo
            )
            VALUES (?, ?, ?, ?, 1)
            """,
            (
                equipo,
                modelo,
                categoria,
                costo_hora
            )
        )

        return int(cur.lastrowid)


# =========================================================
# INTERFAZ ACTIVOS
# =========================================================

def render_activos(usuario: str):

    st.title("🏗️ Gestión de Activos")

    with st.form("crear_activo"):

        st.subheader("Registrar equipo")

        equipo = st.text_input("Equipo")
        modelo = st.text_input("Modelo")
        categoria = st.text_input("Categoría")

        costo_hora = st.number_input(
            "Costo por hora",
            min_value=0.0
        )

        guardar = st.form_submit_button("Registrar activo")

    if guardar:

        try:

            aid = crear_activo(
                usuario,
                equipo,
                modelo,
                categoria,
                costo_hora
            )

            st.success(f"Activo #{aid} registrado")

        except Exception as e:

            st.error("Error registrando activo")
            st.exception(e)

    st.divider()

    try:

        with db_transaction() as conn:

            rows = conn.execute(
                """
                SELECT
                    id,
                    equipo,
                    modelo,
                    categoria,
                    costo_hora
                FROM activos
                WHERE activo=1
                ORDER BY id DESC
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando activos")
        st.exception(e)
        return

    if not rows:

        st.info("No hay activos registrados")
        return

    df = pd.DataFrame(rows)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

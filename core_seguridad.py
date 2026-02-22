# ==========================================================
# CORE DE SEGURIDAD IMPERIO
# ==========================================================

import sqlite3
import streamlit as st


# CONEXIÓN SEGURA
def conectar_db_seguro():

    try:

        conn = sqlite3.connect(
            "database.db",
            timeout=30,
            isolation_level=None
        )

        conn.execute("PRAGMA foreign_keys = ON;")

        return conn

    except Exception as e:

        st.error(f"Error conexión DB: {e}")

        return None


# EJECUCIÓN SEGURA
def ejecutar_seguro(query, params=()):

    conn = conectar_db_seguro()

    if conn is None:

        return None

    try:

        cursor = conn.cursor()

        cursor.execute(query, params)

        conn.commit()

        return cursor

    except Exception as e:

        conn.rollback()

        st.error(f"Error DB: {e}")

        return None

    finally:

        conn.close()


# LECTURA SEGURA
def leer_seguro(query, params=()):

    conn = conectar_db_seguro()

    if conn is None:

        return None

    try:

        import pandas as pd

        df = pd.read_sql(query, conn, params=params)

        return df

    except Exception as e:

        st.error(f"Error lectura DB: {e}")

        return None

    finally:

        conn.close()

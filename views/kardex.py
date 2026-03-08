import streamlit as st
import pandas as pd

from database.connection import db_transaction


def render_kardex(usuario: str):

    st.title("📊 Kardex de Inventario")

    try:

        with db_transaction() as conn:

            rows = conn.execute(
                """
                SELECT
                    fecha,
                    usuario,
                    inventario_id,
                    tipo,
                    cantidad,
                    costo_unitario_usd,
                    referencia
                FROM movimientos_inventario
                ORDER BY fecha DESC
                LIMIT 500
                """
            ).fetchall()

    except Exception as e:

        st.error("Error cargando kardex")
        st.exception(e)
        return

    if not rows:

        st.info("No hay movimientos registrados.")
        return

    df = pd.DataFrame(rows)

    buscar = st.text_input("🔎 Buscar")

    if buscar:
        df = df[
            df.astype(str)
            .apply(lambda x: x.str.contains(buscar, case=False))
            .any(axis=1)
        ]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

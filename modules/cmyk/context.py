import pandas as pd
from database.connection import db_transaction
from modules.cmyk.history import ensure_historial_table


def _table_columns(conn, table: str) -> set[str]:
    """Obtiene columnas existentes en una tabla SQLite."""
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(r[1]) for r in rows}
    except Exception:
        return set()


def _load_contexto_cmyk() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Carga contexto necesario para el módulo CMYK:
    - inventario
    - activos (impresoras)
    - historial de análisis
    """

    ensure_historial_table()

    with db_transaction() as conn:

        # ======================================================
        # INVENTARIO
        # ======================================================

        cols_inv = _table_columns(conn, "inventario")

        df_inv = pd.read_sql_query(
            "SELECT * FROM inventario",
            conn
        )

        if not df_inv.empty:

            if "estado" in cols_inv:

                df_inv = df_inv[
                    df_inv["estado"]
                    .fillna("activo")
                    .str.lower() == "activo"
                ].copy()

            elif "activo" in cols_inv:

                df_inv = df_inv[
                    df_inv["activo"]
                    .fillna(1)
                    .astype(int) == 1
                ].copy()

        # ======================================================
        # ACTIVOS (IMPRESORAS)
        # ======================================================

        cols_act = _table_columns(conn, "activos")

        if cols_act:

            campos = [
                c for c in [
                    "id",
                    "equipo",
                    "nombre",
                    "categoria",
                    "unidad",
                    "modelo",
                    "estado",
                    "activo",
                ]
                if c in cols_act
            ]

            df_act = pd.read_sql_query(
                f"SELECT {', '.join(campos)} FROM activos",
                conn
            )

            if "equipo" not in df_act.columns and "nombre" in df_act.columns:
                df_act = df_act.rename(columns={"nombre": "equipo"})

            if "estado" in df_act.columns:

                df_act = df_act[
                    df_act["estado"]
                    .fillna("activo")
                    .str.lower() == "activo"
                ]

            elif "activo" in df_act.columns:

                df_act = df_act[
                    df_act["activo"]
                    .fillna(1)
                    .astype(int) == 1
                ]

        else:

            df_act = pd.DataFrame(
                columns=[
                    "id",
                    "equipo",
                    "categoria",
                    "unidad",
                    "modelo",
                ]
            )

        # ======================================================
        # HISTORIAL CMYK
        # ======================================================

        df_hist = pd.read_sql_query(
            """
            SELECT
                fecha,
                impresora,
                paginas,
                costo,
                c_ml,
                m_ml,
                y_ml,
                k_ml
            FROM historial_cmyk
            ORDER BY fecha DESC
            LIMIT 100
            """,
            conn,
        )

    return df_inv, df_act, df_hist

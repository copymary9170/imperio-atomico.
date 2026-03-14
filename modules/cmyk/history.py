from typing import Dict
import pandas as pd

from database.connection import db_transaction


# ==========================================================
# UTILIDAD: OBTENER COLUMNAS DE TABLA
# ==========================================================

def _table_columns(conn, table: str) -> set[str]:
    """
    Devuelve el conjunto de columnas existentes en una tabla.
    """
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return {str(r[1]) for r in rows}
    except Exception:
        return set()


# ==========================================================
# ASEGURAR TABLA HISTORIAL
# ==========================================================

def ensure_historial_table() -> None:
    """
    Crea la tabla historial_cmyk si no existe
    y asegura columnas necesarias.
    """

    with db_transaction() as conn:

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS historial_cmyk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                impresora TEXT,
                paginas INTEGER,
                costo REAL,
                fecha DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        cols = _table_columns(conn, "historial_cmyk")

        for c in ["c_ml", "m_ml", "y_ml", "k_ml"]:
            if c not in cols:
                conn.execute(f"ALTER TABLE historial_cmyk ADD COLUMN {c} REAL")


# ==========================================================
# GUARDAR HISTORIAL
# ==========================================================

def guardar_historial(
    impresora: str,
    paginas: int,
    costo: float,
    consumos: Dict[str, float],
) -> None:
    """
    Guarda un registro de análisis CMYK en el historial.
    """

    ensure_historial_table()

    with db_transaction() as conn:

        conn.execute(
            """
            INSERT INTO historial_cmyk
            (impresora, paginas, costo, c_ml, m_ml, y_ml, k_ml)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                impresora,
                int(paginas),
                float(costo),
                float(consumos.get("C", 0.0)),
                float(consumos.get("M", 0.0)),
                float(consumos.get("Y", 0.0)),
                float(consumos.get("K", 0.0)),
            ),
        )


# ==========================================================
# CONSULTAR HISTORIAL
# ==========================================================

def obtener_historial(limit: int = 100) -> pd.DataFrame:
    """
    Devuelve los últimos análisis CMYK guardados.
    """

    ensure_historial_table()

    with db_transaction() as conn:

        df = pd.read_sql_query(
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
            LIMIT ?
            """,
            conn,
            params=(limit,),
        )

    return df


# ==========================================================
# HISTORIAL AGRUPADO POR DÍA
# ==========================================================

def historial_por_dia(limit: int = 100) -> pd.DataFrame:
    """
    Devuelve costo total agrupado por día.
    """

    df = obtener_historial(limit)

    if df.empty:
        return df

    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")

    df_dia = (
        df.dropna(subset=["fecha"])
        .assign(dia=lambda d: d["fecha"].dt.date.astype(str))
        .groupby("dia", as_index=False)["costo"]
        .sum()
    )

    return df_dia


# ==========================================================
# MÉTRICAS GENERALES
# ==========================================================

def metricas_generales() -> Dict[str, float]:
    """
    Devuelve métricas generales del historial.
    """

    ensure_historial_table()

    with db_transaction() as conn:

        row = conn.execute(
            """
            SELECT
                COUNT(*) as trabajos,
                SUM(paginas) as paginas,
                SUM(costo) as costo_total
            FROM historial_cmyk
            """
        ).fetchone()

    if not row:
        return {
            "trabajos": 0,
            "paginas": 0,
            "costo_total": 0.0,
        }

    trabajos, paginas, costo_total = row

    return {
        "trabajos": int(trabajos or 0),
        "paginas": int(paginas or 0),
        "costo_total": float(costo_total or 0.0),
    }

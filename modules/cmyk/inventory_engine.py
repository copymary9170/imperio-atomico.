from typing import Dict
import pandas as pd
from database.connection import db_transaction


# ==========================================================
# BUSCAR COLUMNA
# ==========================================================

def _col(df: pd.DataFrame, candidatos: list[str], default=None):
    for c in candidatos:
        if c in df.columns:
            return c
    return default


# ==========================================================
# FILTRAR TINTAS
# ==========================================================

def filtrar_tintas(df_inv: pd.DataFrame) -> pd.DataFrame:

    if df_inv.empty:
        return pd.DataFrame()

    col_nombre = _col(df_inv, ["item", "nombre"])
    col_categoria = _col(df_inv, ["categoria"])

    if not col_nombre:
        return pd.DataFrame()

    mask = df_inv[col_nombre].fillna("").str.contains(
        "tinta|ink|cyan|cian|magenta|yellow|amarillo|black|negro",
        case=False,
        na=False
    )

    if col_categoria:
        mask = mask | df_inv[col_categoria].fillna("").str.contains(
            "tinta|ink",
            case=False,
            na=False
        )

    return df_inv[mask].copy()


# ==========================================================
# MAPEAR CONSUMO CMYK
# ==========================================================

def mapear_consumo_ids(
    df_tintas: pd.DataFrame,
    totales: Dict[str, float]
) -> Dict[int, float]:

    if df_tintas.empty or "id" not in df_tintas.columns:
        return {}

    col_nombre = _col(df_tintas, ["item", "nombre"])

    alias = {
        "C": ["cian", "cyan"],
        "M": ["magenta"],
        "Y": ["amarillo", "yellow"],
        "K": ["negro", "black"]
    }

    consumos = {}

    for color, ml in totales.items():

        keys = alias.get(color, [])

        if not keys:
            continue

        sub = df_tintas[
            df_tintas[col_nombre]
            .fillna("")
            .str.lower()
            .str.contains("|".join(keys), na=False)
        ]

        if sub.empty:
            continue

        item_id = int(sub.iloc[0]["id"])

        consumos[item_id] = float(consumos.get(item_id, 0.0) + ml)

    return consumos


# ==========================================================
# VALIDAR STOCK
# ==========================================================

def validar_stock(
    df_base: pd.DataFrame,
    consumos_ids: Dict[int, float]
) -> list[str]:

    alertas = []

    if df_base.empty:
        alertas.append("❌ No hay tintas registradas en inventario.")
        return alertas

    if not consumos_ids:
        alertas.append("❌ No se pudieron vincular tintas CMYK con el inventario.")
        return alertas

    col_nombre = _col(df_base, ["item", "nombre"]) or "id"
    col_stock = _col(df_base, ["cantidad", "stock", "existencia"])

    if not col_stock:
        alertas.append("❌ Inventario sin columna de stock.")
        return alertas

    for item_id, requerido in consumos_ids.items():

        fila = df_base[df_base["id"].astype(int) == int(item_id)]

        if fila.empty:
            alertas.append(f"⚠️ No se encontró tinta con ID {item_id}")
            continue

        disponible = float(
            pd.to_numeric(fila[col_stock], errors="coerce")
            .fillna(0)
            .sum()
        )

        if requerido > disponible:

            nombre = str(
                fila.iloc[0].get(col_nombre, f"ID {item_id}")
            )

            alertas.append(
                f"⚠️ Stock insuficiente para {nombre}: "
                f"necesitas {requerido:.2f} ml y hay {disponible:.2f} ml"
            )

    return alertas


# ==========================================================
# DESCONTAR INVENTARIO
# ==========================================================

def descontar_inventario(
    consumos_ids: Dict[int, float]
) -> tuple[bool, str]:

    if not consumos_ids:
        return False, "No se encontraron tintas vinculadas."

    with db_transaction() as conn:

        cols = {
            str(r[1])
            for r in conn.execute(
                "PRAGMA table_info(inventario)"
            ).fetchall()
        }

        col_stock = None

        if "cantidad" in cols:
            col_stock = "cantidad"
        elif "stock" in cols:
            col_stock = "stock"

        if not col_stock:
            return False, "Inventario sin columna de stock."

        for item_id, ml in consumos_ids.items():

            row = conn.execute(
                f"SELECT {col_stock} FROM inventario WHERE id=?",
                (int(item_id),)
            ).fetchone()

            if not row:
                return False, f"No existe item ID {item_id}"

            disponible = float(row[0] or 0)

            if ml > disponible:
                return False, (
                    f"Stock insuficiente ID {item_id}: "
                    f"req {ml:.2f} / disp {disponible:.2f}"
                )

        for item_id, ml in consumos_ids.items():

            conn.execute(
                f"""
                UPDATE inventario
                SET {col_stock} = {col_stock} - ?
                WHERE id = ?
                """,
                (float(ml), int(item_id))
            )

    return True, "Inventario actualizado correctamente."

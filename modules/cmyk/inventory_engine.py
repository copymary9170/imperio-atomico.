from typing import Dict
import pandas as pd

from database.connection import db_transaction


# ==========================================================
# UTILIDAD
# ==========================================================

def _col(df: pd.DataFrame, candidatos: list[str], default=None):
    """
    Devuelve la primera columna existente dentro de una lista de posibles nombres.
    """
    for c in candidatos:
        if c in df.columns:
            return c
    return default


# ==========================================================
# FILTRAR TINTAS DESDE INVENTARIO
# ==========================================================

def filtrar_tintas(
    df_inv: pd.DataFrame,
    impresora_sel: str,
    usar_por_impresora: bool
) -> pd.DataFrame:

    if df_inv.empty:
        return pd.DataFrame()

    col_nombre = _col(df_inv, ["item", "nombre"])
    col_categoria = _col(df_inv, ["categoria"])

    if not col_nombre:
        return pd.DataFrame()

    tintas_mask = df_inv[col_nombre].fillna("").str.contains(
        "tinta|ink|cian|magenta|amarillo|negro|black|cyan",
        case=False,
        na=False,
    )

    if col_categoria:
        tintas_mask = tintas_mask | df_inv[col_categoria].fillna("").str.contains(
            "tinta|insumo",
            case=False,
            na=False,
        )

    base = df_inv[tintas_mask].copy()

    if not usar_por_impresora or base.empty:
        return base

    # -------------------------
    # filtro por impresora
    # -------------------------

    aliases = [impresora_sel.lower().strip()]
    aliases.extend([x for x in aliases[0].split() if len(x) > 2])

    patron = "|".join(sorted(set(a for a in aliases if a)))

    filtro = base[col_nombre].fillna("").str.lower().str.contains(
        patron,
        na=False,
    )

    if filtro.any():
        return base[filtro].copy()

    return base


# ==========================================================
# MAPEAR CONSUMO CMYK → IDs INVENTARIO
# ==========================================================

def mapear_consumo_ids(
    df_tintas: pd.DataFrame,
    totales: Dict[str, float]
) -> Dict[int, float]:

    if df_tintas.empty or "id" not in df_tintas.columns:
        return {}

    col_nombre = _col(df_tintas, ["item", "nombre"])

    if not col_nombre:
        return {}

    alias = {
        "C": ["cian", "cyan"],
        "M": ["magenta"],
        "Y": ["amarillo", "yellow"],
        "K": ["negro", "black"],
    }

    consumos = {}

    for color, ml in totales.items():

        keys = alias.get(color, [])

        if not keys or ml <= 0:
            continue

        sub = df_tintas[
            df_tintas[col_nombre]
            .fillna("")
            .str.lower()
            .str.contains("|".join(keys), na=False)
        ]

        if sub.empty:
            continue

        row = sub.iloc[0]

        item_id = int(row["id"])

        consumos[item_id] = float(
            consumos.get(item_id, 0.0) + ml
        )

    return consumos


# ==========================================================
# VALIDAR STOCK
# ==========================================================

def validar_stock(
    df_base: pd.DataFrame,
    consumos_ids: Dict[int, float]
) -> list[str]:

    if df_base.empty or not consumos_ids:
        return []

    col_nombre = _col(df_base, ["item", "nombre"]) or "id"
    col_cantidad = _col(df_base, ["cantidad", "stock", "existencia"]) or "cantidad"

    if col_cantidad not in df_base.columns or "id" not in df_base.columns:
        return []

    alertas = []

    for item_id, requerido in consumos_ids.items():

        fila = df_base[df_base["id"].astype(int) == int(item_id)]

        if fila.empty:
            alertas.append(
                f"⚠️ No se encontró inventario ID {item_id}"
            )
            continue

        disponible = float(
            pd.to_numeric(fila[col_cantidad], errors="coerce")
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
            for r in conn.execute("PRAGMA table_info(inventario)").fetchall()
        }

        col_cantidad = None

        if "cantidad" in cols:
            col_cantidad = "cantidad"
        elif "stock" in cols:
            col_cantidad = "stock"

        if not col_cantidad:
            return False, "Inventario sin columna de stock."

        # -------------------------
        # verificar stock
        # -------------------------

        for item_id, ml in consumos_ids.items():

            row = conn.execute(
                f"SELECT {col_cantidad} FROM inventario WHERE id=?",
                (int(item_id),),
            ).fetchone()

            if not row:
                return False, f"No existe item ID {item_id}"

            disponible = float(row[0] or 0)

            if ml > disponible:
                return False, (
                    f"Stock insuficiente ID {item_id}: "
                    f"req {ml:.2f} ml / disp {disponible:.2f}"
                )

        # -------------------------
        # descontar
        # -------------------------

        for item_id, ml in consumos_ids.items():

            conn.execute(
                f"""
                UPDATE inventario
                SET {col_cantidad} = {col_cantidad} - ?
                WHERE id = ?
                """,
                (float(ml), int(item_id)),
            )

    return True, "Inventario actualizado correctamente."

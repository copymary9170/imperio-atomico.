from typing import Dict
import re
import unicodedata
import pandas as pd
from database.connection import db_transaction


def _normalize(txt: str) -> str:
    base = unicodedata.normalize("NFKD", str(txt or ""))
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    base = re.sub(r"[^a-zA-Z0-9]+", " ", base).strip().lower()
    return re.sub(r"\s+", " ", base)


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
        "tinta|ink|cyan|cian|magenta|yellow|amarillo|black|negro|cartucho|tricolor",
        case=False,
        na=False
    )

    if col_categoria:
        mask = mask | df_inv[col_categoria].fillna("").str.contains(
            "tinta|ink|cartucho",
            case=False,
            na=False
        )

    return df_inv[mask].copy()


def _score_item(nombre_item: str, printer_name: str, tokens_color: list[str]) -> int:
    nombre_n = _normalize(nombre_item)
    printer_n = _normalize(printer_name)
    score = 0

    if any(tok in nombre_n for tok in tokens_color):
        score += 6

    if "tinta" in nombre_n or "ink" in nombre_n:
        score += 2
    if "cartucho" in nombre_n:
        score += 2

    for token in [t for t in printer_n.split(" ") if len(t) >= 3]:
        if token in nombre_n:
            score += 2

    return score


# ==========================================================
# MAPEAR CONSUMO CMYK
# ==========================================================

def mapear_consumo_ids(
    df_tintas: pd.DataFrame,
    totales: Dict[str, float],
    sistema_tinta: str = "Tanque CMYK (4 tintas)",
    impresora: str = "",
) -> Dict[int, float]:

    if df_tintas.empty or "id" not in df_tintas.columns:
        return {}

    col_nombre = _col(df_tintas, ["item", "nombre"])
    if not col_nombre:
        return {}

    if str(sistema_tinta).startswith("Cartucho"):
        ml_color = float(totales.get("C", 0.0) + totales.get("M", 0.0) + totales.get("Y", 0.0))
        ml_black = float(totales.get("K", 0.0))

        alias_cart = {
            "color": ["cartucho color", "tricolor", "color"],
            "black": ["cartucho negro", "black", "negro", "bk"],
        }
        consumos: Dict[int, float] = {}

        if ml_color > 0:
            mejor_id = None
            mejor_score = 0
            for _, row in df_tintas.iterrows():
                score = _score_item(str(row[col_nombre]), impresora, alias_cart["color"])
                if score > mejor_score:
                    mejor_score = score
                    mejor_id = int(row["id"])
            if mejor_id is not None and mejor_score >= 5:
                consumos[mejor_id] = consumos.get(mejor_id, 0.0) + ml_color

        if ml_black > 0:
            mejor_id = None
            mejor_score = 0
            for _, row in df_tintas.iterrows():
                score = _score_item(str(row[col_nombre]), impresora, alias_cart["black"])
                if score > mejor_score:
                    mejor_score = score
                    mejor_id = int(row["id"])
            if mejor_id is not None and mejor_score >= 5:
                consumos[mejor_id] = consumos.get(mejor_id, 0.0) + ml_black

        return consumos

    alias = {
        "C": ["cian", "cyan", "tinta c", "ink c"],
        "M": ["magenta", "tinta m", "ink m"],
        "Y": ["amarillo", "yellow", "tinta y", "ink y"],
        "K": ["negro", "black", "bk", "tinta k", "ink k"],
    }

    consumos = {}

    for color, ml in totales.items():
        if float(ml) <= 0:
            continue

        keys = alias.get(color, [])
        if not keys:
            continue

        mejor_id = None
        mejor_score = 0
        for _, row in df_tintas.iterrows():
            score = _score_item(str(row[col_nombre]), impresora, keys)
            if score > mejor_score:
                mejor_score = score
                mejor_id = int(row["id"])

        if mejor_id is not None and mejor_score >= 5:
            consumos[mejor_id] = float(consumos.get(mejor_id, 0.0) + ml)

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
    col_stock = _col(df_base, ["stock_actual", "cantidad", "stock", "existencia"])

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

@@ -146,51 +211,53 @@ def validar_stock(
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

        if "stock_actual" in cols:
            col_stock = "stock_actual"
        elif "cantidad" in cols:
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

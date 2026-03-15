import pandas as pd
import streamlit as st

from modules.cmyk.analyzer import analizar_lote, normalizar_imagenes
from modules.cmyk.context import _load_contexto_cmyk
from modules.cmyk.cost_engine import PERFILES_CALIDAD, calcular_costo_lote, costo_tinta_ml
from modules.cmyk.history import guardar_historial, obtener_historial
from modules.cmyk.inventory_engine import (
    descontar_inventario,
    filtrar_tintas,
    mapear_consumo_ids,
    validar_stock,
)
from modules.cmyk.page_size import ajustar_consumo_por_tamano


# ==========================================================
# BASE AUTOMÁTICA DE IMPRENTA
# ==========================================================


def _config_base_imprenta(tamano_pagina: str):
    """Devuelve parámetros base típicos de una imprenta digital."""

    base_por_tamano = {
        "A5": {"costo_desgaste": 0.012, "ml_base": 0.09, "factor_general": 0.90},
        "A4": {"costo_desgaste": 0.020, "ml_base": 0.15, "factor_general": 1.00},
        "Carta": {"costo_desgaste": 0.021, "ml_base": 0.16, "factor_general": 1.02},
        "Oficio": {"costo_desgaste": 0.025, "ml_base": 0.18, "factor_general": 1.08},
        "A3": {"costo_desgaste": 0.034, "ml_base": 0.25, "factor_general": 1.22},
        "Tabloide": {"costo_desgaste": 0.036, "ml_base": 0.27, "factor_general": 1.30},
    }
    return base_por_tamano.get(tamano_pagina, base_por_tamano["A4"])


def _factor_area_personalizada(ancho_mm: float, alto_mm: float) -> float:
    """Factor relativo usando A4 como referencia para tamaños personalizados."""
    area_a4 = 210.0 * 297.0
    area_custom = max(float(ancho_mm), 1.0) * max(float(alto_mm), 1.0)
    return max(0.20, min(4.0, area_custom / area_a4))


def _obtener_perfiles_driver(marca: str):
    """Perfiles de tipo de papel similares a drivers reales para HP y Epson."""
    perfiles_por_marca = {
        "HP": {
            "Papel normal": 1.00,
            "Papeles fotográficos HP": 1.18,
            "Papel profesional o folleto mate HP": 1.12,
            "Papel de presentación mate HP": 1.10,
            "Papel profesional o folleto brillante HP": 1.16,
            "Otr. papeles fotog. inyec tinta": 1.20,
            "Otr. papeles inyec. tinta mates": 1.08,
            "Otr. pap. inyec tinta brillante": 1.14,
            "Papel normal, ligero/reciclado": 0.94,
        },
        "Epson": {
            "Papel normal": 1.00,
            "Epson Photo Paper Glossy": 1.17,
            "Epson Premium Photo Paper Glossy": 1.22,
            "Epson Ultra Premium Photo Paper Glossy": 1.26,
            "Epson Photo Paper Matte": 1.12,
            "Epson Premium Presentation Paper Matte": 1.10,
            "Epson Premium Presentation Paper Matte Double-sided": 1.11,
            "Epson Brochure & Flyer Paper Matte": 1.13,
            "Sobres": 0.96,
        },
    }
    return perfiles_por_marca.get(marca, perfiles_por_marca["HP"])


def _column_match(df: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((c for c in candidates if c in df.columns), None)


def _materiales_papel_disponibles(df_inv: pd.DataFrame) -> pd.DataFrame:
    """Filtra materiales de papel presentes en inventario y con stock positivo."""
    if df_inv.empty:
        return pd.DataFrame()

    df = df_inv.copy()

    col_nombre = _column_match(df, ["nombre", "item", "sku"])
    col_categoria = _column_match(df, ["categoria", "familia", "tipo"])
    col_stock = _column_match(df, ["stock_actual", "stock", "cantidad"])

    if not col_nombre:
        return pd.DataFrame()

    nombres = df[col_nombre].fillna("").astype(str)
    categorias = df[col_categoria].fillna("").astype(str) if col_categoria else ""

    mask_papel_nombre = nombres.str.contains("papel|bond|opalina|couche|glossy|mate|fotograf|cartulina", case=False, na=False)
    if col_categoria:
        mask_papel_categoria = categorias.str.contains("papel|impres|sustrato|material", case=False, na=False)
        mask_papel = mask_papel_nombre | mask_papel_categoria
    else:
        mask_papel = mask_papel_nombre

    df = df[mask_papel].copy()

    if col_stock:
        df["_stock_n"] = pd.to_numeric(df[col_stock], errors="coerce").fillna(0.0)
        df = df[df["_stock_n"] > 0].copy()
    else:
        df["_stock_n"] = 0.0

    col_costo = _column_match(df, ["costo_unitario_usd", "precio_usd", "precio_venta_usd"])
    df["_costo_hoja"] = pd.to_numeric(df[col_costo], errors="coerce").fillna(0.0) if col_costo else 0.0

    col_id = _column_match(df, ["id", "inventario_id"])
    if col_id:
        df["_id"] = df[col_id]
    else:
        df["_id"] = df.index.astype(str)

    df["_material_label"] = df.apply(
        lambda r: f"{str(r[col_nombre]).strip()} | Stock: {float(r['_stock_n']):.2f} | $/hoja: {float(r['_costo_hoja']):.4f}",
        axis=1,
    )

    return df.sort_values(by=["_stock_n", "_costo_hoja"], ascending=[False, True])

def _impresoras_disponibles(df_act: pd.DataFrame) -> list[dict]:
    """Lista impresoras activas detectadas en tabla activos."""
    if df_act is None or df_act.empty:
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


    b1, b2, b3, b4 = st.columns(4)
    if b1.button("🔥 Enviar a Sublimación", use_container_width=True):
        cola = st.session_state.get("cola_sublimacion", [])
        payload_sub = {
            **payload_base,
            "tipo_produccion": "sublimacion",
            "descripcion": f"Transfer CMYK ({total_paginas} páginas)",
            "costo_transfer_total": float(costo_total_con_material),
            "cantidad": int(total_paginas),
        }
        cola.append(payload_sub)
        st.session_state["cola_sublimacion"] = cola
        st.success("Trabajo enviado a la cola de Sublimación.")

    if b2.button("🛠️ Enviar a Otros Procesos", use_container_width=True):
        st.session_state["datos_proceso_desde_cmyk"] = {
            **payload_base,
            "tipo_produccion": "otros_procesos",
            "observacion": f"Costo base CMYK: $ {costo_total_con_material:.2f} | Material: {material_papel}",
        }
        st.success("Trabajo enviado a Otros Procesos.")

    if b3.button("✂️ Enviar a Corte", use_container_width=True):
        st.session_state["datos_corte_desde_cmyk"] = {
            **payload_base,
            "tipo_produccion": "corte",
            "archivo": "Lote CMYK",
            "costo_base": float(costo_total_con_material),
        }
        st.success("Trabajo enviado a Corte como pre-orden.")

    if b4.button("📝 Enviar a Cotización", use_container_width=True):
        st.session_state["datos_pre_cotizacion"] = {
            **payload_base,
            "descripcion": f"Impresión CMYK {total_paginas} pág | {material_papel}",
            "tipo_produccion": "cmyk",
        }
        st.success("Trabajo enviado a Cotizaciones.")

    st.divider()
    st.subheader("Historial reciente")
    st.dataframe(df_hist, use_container_width=True)

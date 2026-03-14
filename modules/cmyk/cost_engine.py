from typing import Dict, Any
import pandas as pd


# ==========================================================
# UTILIDAD
# ==========================================================

def safe_div(a: float, b: float) -> float:
    """División segura evitando división por cero."""
    return float(a) / float(b) if float(b or 0) else 0.0


# ==========================================================
# COSTO PROMEDIO DE TINTA POR ML
# ==========================================================

def costo_tinta_ml(df_tintas: pd.DataFrame, fallback: float) -> float:
    """
    Calcula el costo promedio por ml de tinta usando inventario.
    """

    if df_tintas.empty:
        return fallback

    columnas_posibles = [
        "costo_real_ml",
        "costo_unitario_usd",
        "precio_usd",
        "precio_venta_usd"
    ]

    for col in columnas_posibles:

        if col in df_tintas.columns:

            serie = pd.to_numeric(df_tintas[col], errors="coerce").dropna()
            serie = serie[serie > 0]

            if not serie.empty:
                return float(serie.mean())

    return fallback


# ==========================================================
# COSTO DE IMPRESIÓN POR PÁGINA
# ==========================================================

def calcular_costo_pagina(
    consumo_total_ml: float,
    precio_tinta_ml: float,
    costo_desgaste: float,
    desperdicio_factor: float,
    desgaste_head_ml: float,
    costo_limpieza: float
) -> Dict[str, float]:

    consumo_ajustado = consumo_total_ml * max(1.0, desperdicio_factor)

    costo_tinta = consumo_ajustado * precio_tinta_ml
    costo_desgaste_total = consumo_ajustado * desgaste_head_ml

    costo_total = (
        costo_tinta
        + costo_desgaste
        + costo_desgaste_total
        + costo_limpieza
    )

    return {
        "consumo_ajustado_ml": float(consumo_ajustado),
        "costo_tinta": float(costo_tinta),
        "costo_desgaste": float(costo_desgaste_total),
        "costo_limpieza": float(costo_limpieza),
        "costo_total": float(costo_total),
    }


# ==========================================================
# COSTO DE LOTE
# ==========================================================

def calcular_costo_lote(
    totales_cmyk: Dict[str, float],
    precio_tinta_ml: float,
    paginas: int,
    costo_desgaste_pagina: float,
    desperdicio_factor: float,
    desgaste_head_ml: float,
    costo_limpieza: float
) -> Dict[str, float]:

    total_ml = sum(totales_cmyk.values())

    consumo_ajustado = total_ml * max(1.0, desperdicio_factor)

    costo_tinta = consumo_ajustado * precio_tinta_ml
    costo_desgaste = paginas * costo_desgaste_pagina
    costo_cabezal = consumo_ajustado * desgaste_head_ml

    costo_total = (
        costo_tinta
        + costo_desgaste
        + costo_cabezal
        + costo_limpieza
    )

    return {
        "total_ml": float(total_ml),
        "consumo_ajustado_ml": float(consumo_ajustado),
        "costo_tinta": float(costo_tinta),
        "costo_desgaste": float(costo_desgaste),
        "costo_cabezal": float(costo_cabezal),
        "costo_total": float(costo_total),
        "costo_por_pagina": safe_div(costo_total, paginas),
    }


# ==========================================================
# PERFILES DE CALIDAD
# ==========================================================

PERFILES_CALIDAD = {
    "Borrador": {"ink_mult": 0.82, "wear_mult": 0.90},
    "Normal": {"ink_mult": 1.00, "wear_mult": 1.00},
    "Alta": {"ink_mult": 1.18, "wear_mult": 1.10},
    "Foto": {"ink_mult": 1.32, "wear_mult": 1.15},
}


# ==========================================================
# PERFIL DE PAPEL POR DEFECTO
# ==========================================================

PAPELES_DEFAULT = {
    "Bond 75g": 0.03,
    "Bond 90g": 0.05,
    "Fotográfico Brillante": 0.22,
    "Fotográfico Mate": 0.20,
    "Cartulina": 0.12,
    "Adhesivo": 0.16,
}


# ==========================================================
# DETECTAR PAPELES DESDE INVENTARIO
# ==========================================================

def detectar_papeles(df_inv: pd.DataFrame) -> Dict[str, float]:

    perfiles_papel: Dict[str, float] = {}

    if df_inv.empty:
        return PAPELES_DEFAULT

    posibles_nombre = ["item", "nombre"]
    posibles_precio = [
        "precio_usd",
        "costo_unitario_usd",
        "precio_venta_usd"
    ]

    col_nombre = next((c for c in posibles_nombre if c in df_inv.columns), None)
    col_precio = next((c for c in posibles_precio if c in df_inv.columns), None)

    if not col_nombre or not col_precio:
        return PAPELES_DEFAULT

    papeles = df_inv[
        df_inv[col_nombre]
        .fillna("")
        .str.contains(
            "papel|bond|fotograf|cartulina|adhesivo|opalina|sulfato",
            case=False,
            na=False,
        )
    ].copy()

    if papeles.empty:
        return PAPELES_DEFAULT

    papeles["_precio"] = pd.to_numeric(papeles[col_precio], errors="coerce")
    papeles = papeles[papeles["_precio"] > 0]

    for _, row in papeles.iterrows():
        perfiles_papel[str(row[col_nombre]).strip()] = float(row["_precio"])

    return perfiles_papel or PAPELES_DEFAULT


# ==========================================================
# SIMULADOR PAPEL + CALIDAD
# ==========================================================

def simular_papel_calidad(
    df_inv: pd.DataFrame,
    total_pags: int,
    costo_tinta_base: float,
    costo_desgaste: float
) -> pd.DataFrame:

    perfiles_papel = detectar_papeles(df_inv)

    simulaciones = []

    for papel, costo_hoja in perfiles_papel.items():

        for calidad, cfg in PERFILES_CALIDAD.items():

            tinta_q = costo_tinta_base * float(cfg["ink_mult"])
            desgaste_q = float(costo_desgaste) * float(total_pags) * float(cfg["wear_mult"])
            papel_q = float(total_pags) * float(costo_hoja)

            total_q = tinta_q + desgaste_q + papel_q

            simulaciones.append(
                {
                    "Papel": papel,
                    "Calidad": calidad,
                    "Páginas": int(total_pags),
                    "Tinta ($)": round(tinta_q, 2),
                    "Desgaste ($)": round(desgaste_q, 2),
                    "Papel ($)": round(papel_q, 2),
                    "Total ($)": round(total_q, 2),
                    "Costo por pág ($)": round(safe_div(total_q, total_pags), 4),
                }
            )

    df = pd.DataFrame(simulaciones)

    return df.sort_values("Total ($)")

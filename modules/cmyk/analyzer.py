import io
from typing import List, Tuple, Dict

import numpy as np
from PIL import Image


# ==========================================================
# CONFIGURACIÓN DE SEGURIDAD Y RENDIMIENTO
# ==========================================================

MAX_IMAGE_SIZE = 1500
MAX_PDF_PAGES = 50
MAX_TOTAL_COVERAGE = 3.2


# ==========================================================
# UTILIDADES
# ==========================================================

def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if float(b or 0) else 0.0


def _optimize_image(img: Image.Image) -> Image.Image:

    if img.width > MAX_IMAGE_SIZE or img.height > MAX_IMAGE_SIZE:

        img = img.copy()
        img.thumbnail((MAX_IMAGE_SIZE, MAX_IMAGE_SIZE))

    return img


# ==========================================================
# FACTOR AUTOMÁTICO DE CONSUMO
# ==========================================================

def calcular_factor_consumo(densidad_total: float) -> float:
    """
    Determina automáticamente el factor de consumo
    usando reglas típicas de imprenta.
    """

    if densidad_total < 0.35:
        return 0.9

    elif densidad_total < 0.9:
        return 1.2

    elif densidad_total < 1.5:
        return 1.4

    else:
        return 1.6


# ==========================================================
# NORMALIZAR ARCHIVOS (PDF / IMAGEN)
# ==========================================================

def normalizar_imagenes(archivo) -> List[Tuple[str, Image.Image]]:

    bytes_data = archivo.read()
    nombre = archivo.name

    # ------------------------------------------------------
    # PDF
    # ------------------------------------------------------

    if nombre.lower().endswith(".pdf"):

        try:
            import fitz
        except ModuleNotFoundError:
            raise RuntimeError(
                "PyMuPDF (fitz) es requerido para analizar PDF."
            )

        paginas = []

        doc = fitz.open(stream=bytes_data, filetype="pdf")

        total = min(len(doc), MAX_PDF_PAGES)

        for i in range(total):

            page = doc.load_page(i)

            pix = page.get_pixmap(
                colorspace=fitz.csCMYK,
                dpi=150
            )

            img = Image.frombytes(
                "CMYK",
                [pix.width, pix.height],
                pix.samples
            )

            img = _optimize_image(img)

            paginas.append(
                (f"{nombre} (P{i+1})", img)
            )

        doc.close()

        return paginas

    # ------------------------------------------------------
    # IMAGEN
    # ------------------------------------------------------

    img = Image.open(io.BytesIO(bytes_data)).convert("CMYK")

    img = _optimize_image(img)

    return [(nombre, img)]


# ==========================================================
# ANÁLISIS CMYK
# ==========================================================

def analizar_pagina(
    img_obj: Image.Image,
    ml_base_pagina: float,
    factor_general: float,
    factor_calidad: float,
    factor_papel: float,
    factor_k: float,
    auto_negro_inteligente: bool,
    refuerzo_negro: float,
) -> Dict[str, float]:

    arr = np.asarray(img_obj, dtype=np.float32) / 255.0

    c_chan = arr[:, :, 0]
    m_chan = arr[:, :, 1]
    y_chan = arr[:, :, 2]
    k_chan = arr[:, :, 3]

    c_media = float(np.mean(c_chan))
    m_media = float(np.mean(m_chan))
    y_media = float(np.mean(y_chan))
    k_media = float(np.mean(k_chan))

    densidad_total = float(
        np.mean(c_chan + m_chan + y_chan + k_chan)
    )

    # ------------------------------------------------------
    # LIMITADOR DE TINTA (RIP)
    # ------------------------------------------------------

    if densidad_total > MAX_TOTAL_COVERAGE:

        scale = MAX_TOTAL_COVERAGE / densidad_total

        c_media *= scale
        m_media *= scale
        y_media *= scale
        k_media *= scale

    # ------------------------------------------------------
    # CLASIFICACIÓN DISEÑO
    # ------------------------------------------------------

    if densidad_total < 0.35:
        tipo_diseno = "vector"

    elif densidad_total < 0.9:
        tipo_diseno = "mixto"

    else:
        tipo_diseno = "fotografico"

    # ------------------------------------------------------
    # FACTOR AUTOMÁTICO
    # ------------------------------------------------------

    factor_auto = calcular_factor_consumo(densidad_total)

    base = (
        ml_base_pagina
        * factor_general
        * factor_auto
        * factor_calidad
        * factor_papel
    )

    if tipo_diseno == "fotografico":
        base *= 1.15


    # ------------------------------------------------------
    # CONSUMO
    # ------------------------------------------------------

    ml_c = c_media * base
    ml_m = m_media * base
    ml_y = y_media * base
    ml_k_base = k_media * base * factor_k

    # ------------------------------------------------------
    # NEGRO INTELIGENTE
    # ------------------------------------------------------

    if auto_negro_inteligente:

        cobertura_cmy = (c_chan + m_chan + y_chan) / 3.0

        neutral_mask = (
            (np.abs(c_chan - m_chan) < 0.08)
            & (np.abs(m_chan - y_chan) < 0.08)
        )

        shadow_mask = (
            (k_chan > 0.45)
            | (cobertura_cmy > 0.60)
        )

        rich_black_mask = (
            shadow_mask
            & (cobertura_cmy > 0.35)
        )

        ratio_extra = (
            float(np.mean(shadow_mask)) * 0.12
            + float(np.mean(neutral_mask)) * 0.10
            + float(np.mean(rich_black_mask)) * 0.18
        )

      k_extra_ml = (
            ml_base_pagina
            * factor_general
            * factor_auto
            * factor_calidad
            * factor_papel
            * ratio_extra
        )

    else:

        promedio_color = (c_media + m_media + y_media) / 3.0

        if promedio_color > 0.55:

            k_extra_ml = (
                promedio_color
                * refuerzo_negro
                * factor_auto
            )

        else:

            k_extra_ml = 0.0

    ml_k = ml_k_base + k_extra_ml

    return {
        "C (ml)": float(ml_c),
        "M (ml)": float(ml_m),
        "Y (ml)": float(ml_y),
        "K (ml)": float(ml_k),
        "K extra auto (ml)": float(k_extra_ml),
        "Densidad total": float(densidad_total),
        "Tipo diseño": tipo_diseno,
        "Factor consumo auto": float(factor_auto)
    }


# ==========================================================
# ANÁLISIS DE LOTE
# ==========================================================

def analizar_lote(
    paginas: List[Tuple[str, Image.Image]],
    config: Dict
) -> Tuple[list, Dict[str, float]]:

    resultados = []

    totales = {
        "C": 0.0,
        "M": 0.0,
        "Y": 0.0,
        "K": 0.0
    }

    for nombre, img in paginas:

        analisis = analizar_pagina(
            img_obj=img,
            ml_base_pagina=config["ml_base_pagina"],
            factor_general=config["factor_general"],
            factor_calidad=config["factor_calidad"],
            factor_papel=config["factor_papel"],
            factor_k=config["factor_k"],
            auto_negro_inteligente=config["auto_negro_inteligente"],
            refuerzo_negro=config["refuerzo_negro"],
        )

        totales["C"] += analisis["C (ml)"]
        totales["M"] += analisis["M (ml)"]
        totales["Y"] += analisis["Y (ml)"]
        totales["K"] += analisis["K (ml)"]

        resultados.append({
            "archivo": nombre,
            **analisis
        })

    return resultados, totales

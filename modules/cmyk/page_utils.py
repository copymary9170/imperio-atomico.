# ==========================================================
# PERFILES DE TAMAÑO DE PAPEL
# ==========================================================

PAGE_SIZES = {
    "A5": (148, 210),
    "A4": (210, 297),
    "A3": (297, 420),
    "Carta": (216, 279),
    "Oficio": (216, 356),
    "Tabloide": (279, 432),
}


# ==========================================================
# CALCULAR ÁREA
# ==========================================================

def page_area_mm(width_mm: float, height_mm: float) -> float:
    """
    Calcula el área de una página en milímetros cuadrados.
    """
    return float(width_mm) * float(height_mm)


# ==========================================================
# FACTOR RELATIVO DE TINTA
# ==========================================================

def page_area_factor(page_name: str, base_page: str = "A4") -> float:
    """
    Devuelve cuánto más grande o pequeño es un papel
    comparado con el tamaño base (por defecto A4).

    Ejemplo:
    A3 = 2x A4
    """

    if page_name not in PAGE_SIZES or base_page not in PAGE_SIZES:
        return 1.0

    w, h = PAGE_SIZES[page_name]
    bw, bh = PAGE_SIZES[base_page]

    area_page = page_area_mm(w, h)
    area_base = page_area_mm(bw, bh)

    return area_page / area_base


# ==========================================================
# AJUSTAR CONSUMO DE TINTA
# ==========================================================

def ajustar_consumo_por_papel(
    consumo_ml: float,
    page_name: str,
    base_page: str = "A4"
) -> float:
    """
    Ajusta consumo de tinta dependiendo del tamaño del papel.
    """

    factor = page_area_factor(page_name, base_page)

    return consumo_ml * factor

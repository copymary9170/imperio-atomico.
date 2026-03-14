# ==========================================================
# TAMAÑOS DE PÁGINA ESTÁNDAR (mm)
# ==========================================================

PAGE_SIZES_MM = {
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

def page_area(width_mm: float, height_mm: float) -> float:
    """Área de una página en mm²."""
    return float(width_mm) * float(height_mm)


# ==========================================================
# FACTOR DE ESCALA DE TINTA
# ==========================================================

def page_scale_factor(page_name: str, base_page: str = "A4") -> float:
    """
    Calcula cuánto más grande o pequeño es un papel
    comparado con el tamaño base (A4 por defecto).
    """

    if page_name not in PAGE_SIZES_MM:
        return 1.0

    if base_page not in PAGE_SIZES_MM:
        return 1.0

    w, h = PAGE_SIZES_MM[page_name]
    bw, bh = PAGE_SIZES_MM[base_page]

    area_page = page_area(w, h)
    area_base = page_area(bw, bh)

    return area_page / area_base


# ==========================================================
# AJUSTAR CONSUMO POR TAMAÑO DE PÁGINA
# ==========================================================

def ajustar_consumo_por_tamano(
    consumo_ml: float,
    page_name: str,
    base_page: str = "A4"
) -> float:
    """
    Ajusta consumo de tinta según tamaño de página.
    """

    factor = page_scale_factor(page_name, base_page)

    return consumo_ml * factor

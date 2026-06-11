from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostoCabezal:
    cantidad_cabezales: float
    costo_total_cabezales_usd: float
    vida_util_paginas: float
    costo_cabezal_por_pagina_usd: float
    costo_cabezal_por_trabajo_usd: float


def calcular_costo_cabezales(
    *,
    cantidad_cabezales: float,
    costo_unitario_cabezal_usd: float,
    vida_util_paginas: float,
    paginas_trabajo: float = 1.0,
) -> CostoCabezal:
    """Prorratea el costo de cabezales por página o trabajo.

    Útil para impresoras de tanque como HP Smart Tank, Epson EcoTank u otras
    máquinas donde el cabezal es una pieza de desgaste aparte de la tinta.

    Ejemplo:
    - 2 cabezales × $50 = $100
    - vida estimada: 12000 páginas
    - costo cabezal por página: $0.00833
    """
    cantidad = max(0.0, float(cantidad_cabezales or 0.0))
    costo_unit = max(0.0, float(costo_unitario_cabezal_usd or 0.0))
    vida = max(0.0, float(vida_util_paginas or 0.0))
    paginas = max(0.0, float(paginas_trabajo or 0.0))

    total = cantidad * costo_unit
    costo_pagina = total / vida if vida > 0 else 0.0
    costo_trabajo = costo_pagina * paginas

    return CostoCabezal(
        cantidad_cabezales=round(cantidad, 4),
        costo_total_cabezales_usd=round(total, 4),
        vida_util_paginas=round(vida, 4),
        costo_cabezal_por_pagina_usd=round(costo_pagina, 6),
        costo_cabezal_por_trabajo_usd=round(costo_trabajo, 6),
    )

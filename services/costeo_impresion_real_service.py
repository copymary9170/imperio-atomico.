from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from services.cabezales_costeo_service import calcular_costo_cabezales
from services.impresora_consumibles_service import listar_consumibles_por_impresora


@dataclass(frozen=True)
class CostoImpresionReal:
    activo_id: int
    paginas: float
    costo_consumibles_usd: float
    costo_cabezales_usd: float
    costo_total_tecnico_usd: float
    costo_por_pagina_usd: float
    detalle: list[dict[str, Any]]


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _inferir_consumo_por_pagina(row: pd.Series, paginas: float) -> tuple[float, float, str]:
    """Devuelve costo total, costo por página y método usado para una relación.

    Prioridad:
    1. costo_estimado_hoja_usd si fue indicado manualmente.
    2. costo_unitario_usd / rendimiento_paginas si hay rendimiento.
    3. 0 si no hay datos suficientes.
    """
    costo_manual = _safe_float(row.get("costo_estimado_hoja_usd"), 0.0)
    if costo_manual > 0:
        return costo_manual * paginas, costo_manual, "costo manual por impresión"

    costo_unitario = _safe_float(row.get("costo_unitario_usd"), 0.0)
    rendimiento = _safe_float(row.get("rendimiento_paginas"), 0.0)
    if costo_unitario > 0 and rendimiento > 0:
        costo_pagina = costo_unitario / rendimiento
        return costo_pagina * paginas, costo_pagina, "costo inventario / rendimiento"

    return 0.0, 0.0, "sin costo suficiente"


def calcular_costo_impresion_real(
    *,
    activo_id: int,
    paginas: float,
    incluir_cabezales: bool = False,
    cantidad_cabezales: float = 0.0,
    costo_unitario_cabezal_usd: float = 0.0,
    vida_util_cabezales_paginas: float = 0.0,
    impuestos_cabezales_pct: float = 0.0,
    delivery_cabezales_usd: float = 0.0,
    comision_cabezales_usd: float = 0.0,
) -> CostoImpresionReal:
    """Calcula el costo técnico de impresión usando consumibles asociados a una impresora.

    No incluye papel, electricidad, internet, mano de obra ni margen. Es la base técnica
    de consumibles de máquina: tintas, cartuchos, tóner, rollos, ribbon y cabezales.
    """
    activo_ok = int(activo_id)
    paginas_ok = max(0.0, float(paginas or 0.0))
    consumibles = listar_consumibles_por_impresora(activo_ok)

    detalle: list[dict[str, Any]] = []
    total_consumibles = 0.0

    if not consumibles.empty and paginas_ok > 0:
        for _, row in consumibles.iterrows():
            costo_total, costo_pagina, metodo = _inferir_consumo_por_pagina(row, paginas_ok)
            total_consumibles += costo_total
            detalle.append(
                {
                    "consumible": row.get("consumible"),
                    "tipo": row.get("tipo_consumible"),
                    "color": row.get("color"),
                    "unidad": row.get("unidad_carga") or row.get("unidad"),
                    "rendimiento_paginas": _safe_float(row.get("rendimiento_paginas"), 0.0),
                    "costo_por_pagina_usd": round(costo_pagina, 6),
                    "costo_total_usd": round(costo_total, 6),
                    "metodo": metodo,
                }
            )

    costo_cabezales = 0.0
    if incluir_cabezales and paginas_ok > 0:
        cab = calcular_costo_cabezales(
            cantidad_cabezales=cantidad_cabezales,
            costo_unitario_cabezal_usd=costo_unitario_cabezal_usd,
            vida_util_paginas=vida_util_cabezales_paginas,
            paginas_trabajo=paginas_ok,
            impuestos_pct=impuestos_cabezales_pct,
            delivery_usd=delivery_cabezales_usd,
            comision_pago_usd=comision_cabezales_usd,
        )
        costo_cabezales = cab.costo_cabezal_por_trabajo_usd
        detalle.append(
            {
                "consumible": "Cabezales",
                "tipo": "desgaste tecnico",
                "color": "No aplica",
                "unidad": "pagina",
                "rendimiento_paginas": cab.vida_util_paginas,
                "costo_por_pagina_usd": cab.costo_cabezal_por_pagina_usd,
                "costo_total_usd": cab.costo_cabezal_por_trabajo_usd,
                "metodo": "costo real cabezales / vida util",
            }
        )

    total = total_consumibles + costo_cabezales
    costo_pagina_total = total / paginas_ok if paginas_ok > 0 else 0.0

    return CostoImpresionReal(
        activo_id=activo_ok,
        paginas=round(paginas_ok, 4),
        costo_consumibles_usd=round(total_consumibles, 6),
        costo_cabezales_usd=round(costo_cabezales, 6),
        costo_total_tecnico_usd=round(total, 6),
        costo_por_pagina_usd=round(costo_pagina_total, 6),
        detalle=detalle,
    )

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CostoRealCompra:
    base_usd: float
    impuesto_usd: float
    delivery_usd: float
    comision_pago_usd: float
    total_real_usd: float
    costo_unitario_real_usd: float


def calcular_costo_real_compra(
    *,
    costo_base_usd: float,
    cantidad: float,
    impuestos_pct: float = 0.0,
    delivery_usd: float = 0.0,
    comision_pago_usd: float = 0.0,
) -> CostoRealCompra:
    """Calcula el costo real de una compra de inventario.

    Incluye precio base, impuestos, delivery/envío y comisión del método de pago.
    La cantidad debe venir ya convertida a la unidad real de inventario: ml, unidad,
    rollo, cartucho, hoja, gramo, etc.
    """
    cantidad_ok = float(cantidad or 0.0)
    if cantidad_ok <= 0:
        raise ValueError("La cantidad comprada debe ser mayor que cero.")

    base = max(0.0, float(costo_base_usd or 0.0))
    impuestos = max(0.0, float(impuestos_pct or 0.0))
    delivery = max(0.0, float(delivery_usd or 0.0))
    comision = max(0.0, float(comision_pago_usd or 0.0))

    impuesto_usd = base * (impuestos / 100.0)
    total = base + impuesto_usd + delivery + comision
    costo_unitario = total / cantidad_ok

    return CostoRealCompra(
        base_usd=round(base, 4),
        impuesto_usd=round(impuesto_usd, 4),
        delivery_usd=round(delivery, 4),
        comision_pago_usd=round(comision, 4),
        total_real_usd=round(total, 4),
        costo_unitario_real_usd=round(costo_unitario, 6),
    )

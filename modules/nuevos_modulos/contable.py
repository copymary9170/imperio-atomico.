from __future__ import annotations

from .types import ModuleBlueprint

CONTABLE_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="impuestos",
        name="Impuestos",
        icon="🧾",
        category="Contabilidad",
        summary="Calcula impuestos automáticamente y soporta obligaciones fiscales periódicas.",
        capabilities=(
            "Cálculo automático de IVA",
            "Reportes fiscales",
            "Declaraciones",
        ),
        integrations=("Ventas", "Compras", "Contabilidad", "Tesorería"),
        business_value="Reduce errores fiscales y acelera el cumplimiento tributario.",
        priority="Alta",
    ),
    ModuleBlueprint(
        key="conciliacion_bancaria",
        name="Conciliación bancaria",
        icon="🏛️",
        category="Contabilidad",
        summary="Compara movimientos del sistema contra extractos bancarios para detectar diferencias.",
        capabilities=(
            "Comparar sistema vs banco",
            "Detectar diferencias",
            "Validar ingresos reales",
        ),
        integrations=("Tesorería", "Ventas", "Contabilidad", "Caja"),
        business_value="Aumenta control financiero y evita desbalances entre caja, banco y sistema.",
        priority="Alta",
    ),
)

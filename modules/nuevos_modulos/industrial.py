from __future__ import annotations

from .types import ModuleBlueprint

INDUSTRIAL_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="mantenimiento_activos",
        name="Mantenimiento de activos",
        icon="🛠️",
        category="Operación industrial",
        summary="Pasa de diagnóstico reactivo a mantenimiento preventivo y correctivo planificado.",
        capabilities=(
            "Historial de mantenimiento",
            "Mantenimientos preventivos",
            "Alertas por uso",
            "Costos de reparación",
        ),
        integrations=("Activos", "Diagnóstico", "Producción", "Costos"),
        business_value="Reduce paradas no planificadas y extiende la vida útil de equipos críticos de imprenta.",
        priority="Alta",
    ),

    ModuleBlueprint(
        key="rutas_produccion",
        name="Rutas de producción",
        icon="🧭",
        category="Operación industrial",
        summary="Define el routing de fabricación para convertir trabajos complejos en pasos operativos controlables.",
        capabilities=(
            "Diseño → impresión → corte → sublimado → entrega",
            "Secuencias estándar por tipo de trabajo",
            "Tiempos por operación",
        ),
        integrations=("Planificación", "Producción", "Costeo", "Calidad"),
        business_value="Convierte la operación en un flujo industrial repetible y medible.",
        priority="Alta",
    ),
)

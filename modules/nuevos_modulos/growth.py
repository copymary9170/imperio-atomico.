from __future__ import annotations

from .types import ModuleBlueprint

GROWTH_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="crm",
        name="CRM",
        icon="🤝",
        category="Negocio y crecimiento",
        summary="Convierte la base de clientes en un sistema de seguimiento comercial con historial completo.",
        capabilities=(
            "Historial completo",
            "Seguimiento de clientes",
            "Clientes frecuentes",
            "Campañas",
        ),
        integrations=("Clientes", "Ventas", "Marketing", "Fidelización"),
        business_value="Aumenta recurrencia, seguimiento y valor de vida del cliente.",
        priority="Media-Alta",
    ),
    ModuleBlueprint(
        key="marketing_ventas",
        name="Marketing / Ventas",
        icon="📣",
        category="Negocio y crecimiento",
        summary="Gestiona promociones y analiza la respuesta comercial para vender mejor.",
        capabilities=(
            "Promociones",
            "Descuentos",
            "Combos",
            "Análisis de ventas",
        ),
        integrations=("CRM", "Ventas", "Catálogo", "Fidelización"),
        business_value="Ayuda a mover inventario, impulsar campañas y medir qué estrategias sí convierten.",
        priority="Media",
    ),
    ModuleBlueprint(
        key="fidelizacion",
        name="Fidelización",
        icon="⭐",
        category="Negocio y crecimiento",
        summary="Premia recurrencia con beneficios para clientes frecuentes y VIP.",
        capabilities=(
            "Puntos",
            "Descuentos por recurrencia",
            "Clientes VIP",
        ),
        integrations=("CRM", "Ventas", "Marketing"),
        business_value="Incrementa recompra y fortalece relaciones con clientes de alto valor.",
        priority="Media",
    ),

    

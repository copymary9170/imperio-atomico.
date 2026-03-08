"""
Servicios de dominio y aplicación.

Este módulo expone los servicios principales del sistema mediante
lazy loading para evitar cargar módulos innecesarios al iniciar.
"""

from importlib import import_module

__all__ = [
    "CotizacionService",
    "DiagnosticsService",
    "InventoryMovement",
    "InventoryService",
    "ConsumoInsumo",
    "ProduccionService",
    "VentaItem",
    "VentasService",
    "analizar_hoja_diagnostico",
    "extraer_contador_impresiones",
    "extraer_texto_diagnostico",
]


# Mapa de exportaciones perezosas
_EXPORTS = {

    # Cotizaciones
    "CotizacionService": ("services.cotizacion_service", "CotizacionService"),

    # Diagnósticos
    "DiagnosticsService": ("services.diagnostics_service", "DiagnosticsService"),
    "analizar_hoja_diagnostico": ("services.diagnostics_service", "analizar_hoja_diagnostico"),
    "extraer_contador_impresiones": ("services.diagnostics_service", "extraer_contador_impresiones"),
    "extraer_texto_diagnostico": ("services.diagnostics_service", "extraer_texto_diagnostico"),

    # Inventario
    "InventoryMovement": ("services.inventario_service", "InventoryMovement"),
    "InventoryService": ("services.inventario_service", "InventoryService"),

    # Producción
    "ConsumoInsumo": ("services.produccion_service", "ConsumoInsumo"),
    "ProduccionService": ("services.produccion_service", "ProduccionService"),

    # Ventas
    "VentaItem": ("services.ventas_service", "VentaItem"),
    "VentasService": ("services.ventas_service", "VentasService"),
}


def __getattr__(name):

    if name not in _EXPORTS:
        raise AttributeError(f"services: atributo '{name}' no existe")

    module_name, attr_name = _EXPORTS[name]

    module = import_module(module_name)

    value = getattr(module, attr_name)

    globals()[name] = value

    return value

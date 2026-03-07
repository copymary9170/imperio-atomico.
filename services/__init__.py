"""Paquete de servicios de dominio/aplicación.

Mantiene imports perezosos para evitar cargar módulos no utilizados durante el arranque.
"""

from importlib import import_module

__all__ = [
    "ConsumoInsumo",
    "CotizacionService",
    "DiagnosticsService",
    "InventoryMovement",
    "InventoryService",
    "ProduccionService",
    "VentaItem",
    "VentasService",
    "analizar_hoja_diagnostico",
    "extraer_contador_impresiones",
    "extraer_texto_diagnostico",
]

_EXPORTS = {
    "CotizacionService": ("services.cotizacion_service", "CotizacionService"),
    "DiagnosticsService": ("services.diagnostics_service", "DiagnosticsService"),
    "analizar_hoja_diagnostico": ("services.diagnostics_service", "analizar_hoja_diagnostico"),
    "extraer_contador_impresiones": ("services.diagnostics_service", "extraer_contador_impresiones"),
    "extraer_texto_diagnostico": ("services.diagnostics_service", "extraer_texto_diagnostico"),
    "InventoryMovement": ("services.inventario_service", "InventoryMovement"),
    "InventoryService": ("services.inventario_service", "InventoryService"),
    "ConsumoInsumo": ("services.produccion_service", "ConsumoInsumo"),
    "ProduccionService": ("services.produccion_service", "ProduccionService"),
    "VentaItem": ("services.ventas_service", "VentaItem"),
    "VentasService": ("services.ventas_service", "VentasService"),
}


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(f"module 'services' has no attribute {name!r}")

    module_name, attr_name = _EXPORTS[name]
    module = import_module(module_name)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

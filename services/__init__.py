"""
Servicios de dominio y aplicación.

Este módulo expone los servicios principales del sistema mediante
lazy loading para evitar cargar módulos innecesarios al iniciar.
"""

from importlib import import_module

__all__ = [
    "CotizacionService",
    "CompraFinancialInput",
    "DiagnosticsService",
    "InventoryMovement",
    "InventoryService",
    "ConsumoInsumo",
    "ProduccionService",
    "crear_cuenta_por_pagar_desde_compra",
    "listar_movimientos_tesoreria",
    "listar_vencimientos",
    "obtener_resumen_tesoreria",
    "registrar_egreso",
    "registrar_ingreso",
    "registrar_movimiento_tesoreria",
    "registrar_pago_cuenta_por_pagar",
    "validar_condicion_compra",
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
    "CompraFinancialInput": ("services.cxp_proveedores_service", "CompraFinancialInput"),

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

    # Compras / CxP proveedores
    "crear_cuenta_por_pagar_desde_compra": ("services.cxp_proveedores_service", "crear_cuenta_por_pagar_desde_compra"),
    "listar_movimientos_tesoreria": ("services.tesoreria_service", "listar_movimientos_tesoreria"),
    "listar_vencimientos": ("services.tesoreria_service", "listar_vencimientos"),
    "obtener_resumen_tesoreria": ("services.tesoreria_service", "obtener_resumen_tesoreria"),
    "registrar_egreso": ("services.tesoreria_service", "registrar_egreso"),
    "registrar_ingreso": ("services.tesoreria_service", "registrar_ingreso"),
    "registrar_movimiento_tesoreria": ("services.tesoreria_service", "registrar_movimiento_tesoreria"),
    "registrar_pago_cuenta_por_pagar": ("services.cxp_proveedores_service", "registrar_pago_cuenta_por_pagar"),
    "validar_condicion_compra": ("services.cxp_proveedores_service", "validar_condicion_compra"),

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

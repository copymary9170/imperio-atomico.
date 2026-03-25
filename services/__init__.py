"""
Servicios de dominio y aplicación.

Este módulo expone los servicios principales del sistema mediante
lazy loading para evitar cargar módulos innecesarios al iniciar.
"""

from importlib import import_module

__all__ = [
    "CotizacionService",
    "AsientoLinea",
    "CompraFinancialInput",
    "DiagnosticsService",
    "InventoryMovement",
    "InventoryService",
    "ConsumoInsumo",
    "ProduccionService",
    "crear_cuenta_por_pagar_desde_compra",
    "contabilizar_ajuste_manual_tesoreria",
    "contabilizar_cobro_cliente",
    "contabilizar_compra",
    "contabilizar_gasto",
    "contabilizar_pago_proveedor",
    "contabilizar_venta",
    "conciliar_movimientos",
    "cerrar_periodo",
    "CobranzaInput",
    "listar_cierres_periodo",
    "listar_movimientos_bancarios",
    "listar_movimientos_tesoreria_pendientes",
    "listar_movimientos_tesoreria",
    "listar_vencimientos",
    "obtener_reporte_fiscal_simple",
    "obtener_resumen_fiscal_periodo",
    "obtener_detalle_fiscal_periodo",
    "exportar_resumen_fiscal_csv",
    "obtener_resumen_cierre_periodo",
    "obtener_resumen_conciliacion",
    "obtener_resumen_tesoreria",
    "periodo_desde_fecha",
    "periodo_esta_cerrado",
    "registrar_egreso",
    "registrar_ingreso",
    "registrar_movimiento_bancario",
    "registrar_movimiento_tesoreria",
    "registrar_pago_cuenta_por_pagar",
    "registrar_abono_cuenta_por_cobrar",
    "registrar_gestion_cobranza",
    "marcar_cuenta_incobrable",
    "obtener_reporte_cartera",
    "sincronizar_contabilidad",
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
    "AsientoLinea": ("services.contabilidad_service", "AsientoLinea"),
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
    "CobranzaInput": ("services.cxc_cobranza_service", "CobranzaInput"),
    "contabilizar_ajuste_manual_tesoreria": ("services.contabilidad_service", "contabilizar_ajuste_manual_tesoreria"),
    "contabilizar_cobro_cliente": ("services.contabilidad_service", "contabilizar_cobro_cliente"),
    "contabilizar_compra": ("services.contabilidad_service", "contabilizar_compra"),
    "contabilizar_gasto": ("services.contabilidad_service", "contabilizar_gasto"),
    "contabilizar_pago_proveedor": ("services.contabilidad_service", "contabilizar_pago_proveedor"),
    "contabilizar_venta": ("services.contabilidad_service", "contabilizar_venta"),
    "conciliar_movimientos": ("services.conciliacion_service", "conciliar_movimientos"),
    "cerrar_periodo": ("services.conciliacion_service", "cerrar_periodo"),
    "listar_cierres_periodo": ("services.conciliacion_service", "listar_cierres_periodo"),
    "listar_movimientos_bancarios": ("services.conciliacion_service", "listar_movimientos_bancarios"),
    "listar_movimientos_tesoreria_pendientes": ("services.conciliacion_service", "listar_movimientos_tesoreria_pendientes"),
    "listar_movimientos_tesoreria": ("services.tesoreria_service", "listar_movimientos_tesoreria"),
    "listar_vencimientos": ("services.tesoreria_service", "listar_vencimientos"),
   "obtener_reporte_fiscal_simple": ("services.conciliacion_service", "obtener_reporte_fiscal_simple"),
    "obtener_resumen_fiscal_periodo": ("services.fiscal_service", "obtener_resumen_fiscal_periodo"),
    "obtener_detalle_fiscal_periodo": ("services.fiscal_service", "obtener_detalle_fiscal_periodo"),
    "exportar_resumen_fiscal_csv": ("services.fiscal_service", "exportar_resumen_fiscal_csv"),
    "obtener_resumen_cierre_periodo": ("services.conciliacion_service", "obtener_resumen_cierre_periodo"),
    "obtener_resumen_conciliacion": ("services.conciliacion_service", "obtener_resumen_conciliacion"),
    "obtener_resumen_tesoreria": ("services.tesoreria_service", "obtener_resumen_tesoreria"),
    "periodo_desde_fecha": ("services.conciliacion_service", "periodo_desde_fecha"),
    "periodo_esta_cerrado": ("services.conciliacion_service", "periodo_esta_cerrado"),
    "registrar_egreso": ("services.tesoreria_service", "registrar_egreso"),
    "registrar_ingreso": ("services.tesoreria_service", "registrar_ingreso"),
    "registrar_movimiento_bancario": ("services.conciliacion_service", "registrar_movimiento_bancario"),
    "registrar_movimiento_tesoreria": ("services.tesoreria_service", "registrar_movimiento_tesoreria"),
    "registrar_pago_cuenta_por_pagar": ("services.cxp_proveedores_service", "registrar_pago_cuenta_por_pagar"),
    "registrar_abono_cuenta_por_cobrar": ("services.cxc_cobranza_service", "registrar_abono_cuenta_por_cobrar"),
    "registrar_gestion_cobranza": ("services.cxc_cobranza_service", "registrar_gestion_cobranza"),
    "marcar_cuenta_incobrable": ("services.cxc_cobranza_service", "marcar_cuenta_incobrable"),
    "obtener_reporte_cartera": ("services.cxc_cobranza_service", "obtener_reporte_cartera"),
    "sincronizar_contabilidad": ("services.contabilidad_service", "sincronizar_contabilidad"),
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

from __future__ import annotations

from .admin import ADMIN_MODULES
from .contable import CONTABLE_MODULES
from .finanzas import FINANZAS_MODULES
from .growth import GROWTH_MODULES
from .industrial import INDUSTRIAL_MODULES
from .types import DataFlow, ModuleBlueprint

MODULE_BLUEPRINTS: tuple[ModuleBlueprint, ...] = (
    *FINANZAS_MODULES,
    *INDUSTRIAL_MODULES,
    *CONTABLE_MODULES,
    *GROWTH_MODULES,
    *ADMIN_MODULES,
)
MODULE_BY_KEY = {module.key: module for module in MODULE_BLUEPRINTS}

CATEGORY_LABELS = {
    "finanzas": "💼 Finanzas operativas",
    "industrial": "🏭 Operación industrial",
    "contable": "💰 Contabilidad",
    "growth": "📈 Negocio y crecimiento",
    "admin": "👨‍💼 Administración interna",
}
CATEGORY_KEYS = {
    "finanzas": tuple(module.key for module in FINANZAS_MODULES),
    "industrial": tuple(module.key for module in INDUSTRIAL_MODULES),
    "contable": tuple(module.key for module in CONTABLE_MODULES),
    "growth": tuple(module.key for module in GROWTH_MODULES),
    "admin": tuple(module.key for module in ADMIN_MODULES),
}

MODULE_DATA_FLOWS: tuple[DataFlow, ...] = (
    DataFlow("compras_proveedores", "cuentas_por_pagar", "Órdenes aprobadas y facturas", "Tiempo real"),
    DataFlow("cuentas_por_pagar", "tesoreria", "Calendario de vencimientos", "Diario"),
    DataFlow("tesoreria", "conciliacion_bancaria", "Movimientos de caja y bancos", "Diario"),
    DataFlow("produccion", "costeo_industrial", "Consumo de materiales y horas", "Por orden"),
    DataFlow("control_calidad", "mermas_desperdicio", "Rechazos y reprocesos", "Por lote"),
    DataFlow("crm", "marketing_ventas", "Segmentos y comportamiento", "Semanal"),
    DataFlow("rrhh", "seguridad_roles", "Altas/bajas de personal", "Tiempo real"),
)


def get_related_flows(module_key: str) -> tuple[DataFlow, ...]:
    return tuple(
        flow
        for flow in MODULE_DATA_FLOWS
        if flow.source == module_key or flow.target == module_key
    )

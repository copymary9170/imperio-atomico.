from __future__ import annotations

from .types import ModuleBlueprint

FINANZAS_MODULES: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="cuentas_por_pagar",
        name="Cuentas por pagar",
        icon="💸",
        category="Finanzas operativas",
        summary="Controla obligaciones con proveedores, vencimientos y salidas de efectivo pendientes.",
        capabilities=(
            "Deudas con proveedores",
            "Pagos pendientes",
            "Fechas de vencimiento",
            "Control de flujo de salida",
        ),
        integrations=("Compras", "Tesorería", "Contabilidad", "Gastos"),
        business_value="Evita atrasos, intereses y desorden financiero al consolidar las obligaciones de pago del negocio.",
        priority="Crítica",
    ),
    ModuleBlueprint(
        key="tesoreria",
        name="Tesorería / Flujo de caja",
        icon="🏦",
        category="Finanzas operativas",
        summary="Proyecta liquidez, concentra entradas/salidas y anticipa semanas con presión de caja.",
        capabilities=(
            "Entradas vs salidas",
            "Proyección de efectivo",
            "Alertas de liquidez",
            "Balance diario/semanal",
        ),
        integrations=("Caja", "Ventas", "Cuentas por cobrar", "Cuentas por pagar"),
        business_value="Permite saber si el negocio puede operar, pagar proveedores y sostener crecimiento sin quedarse sin efectivo.",
        priority="Crítica",
    ),
    ModuleBlueprint(
        key="costeo_industrial",
        name="Costos / Costeo industrial",
        icon="🧮",
        category="Finanzas operativas",
        summary="Unifica el cálculo del costo real por producto, orden y servicio para medir margen real.",
        capabilities=(
            "Costo real por producto",
            "Costo por orden de producción",
            "Costo por servicio",
            "Margen real",
        ),
        integrations=("CMYK", "Producción", "Cotizaciones", "Inventario", "Gastos"),
        business_value="Conecta todos los procesos del ERP en una sola lógica de costo y protege la rentabilidad.",
        priority="Crítica",
    ),

)

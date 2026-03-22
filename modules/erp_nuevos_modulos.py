from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class ModuleBlueprint:
    key: str
    name: str
    icon: str
    category: str
    summary: str
    capabilities: tuple[str, ...]
    integrations: tuple[str, ...]
    business_value: str
    priority: str


MODULE_BLUEPRINTS: tuple[ModuleBlueprint, ...] = (
    ModuleBlueprint(
        key="compras_proveedores",
        name="Compras / Proveedores",
        icon="🚚",
        category="Finanzas operativas",
        summary="Formaliza abastecimiento, negociación y control de compras para alimentar inventario y costos reales.",
        capabilities=(
            "Registro de proveedores",
            "Órdenes de compra",
            "Recepción de mercancía",
            "Precios por proveedor",
            "Historial de compras",
            "Cuentas por pagar a proveedores",
        ),
        integrations=("Inventario", "Gastos", "Costos reales", "Tesorería"),
        business_value="Da trazabilidad al abastecimiento y permite comprar mejor, comparar proveedores y alimentar el costo real del ERP.",
        priority="Alta",
    ),
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
    ModuleBlueprint(
        key="mermas_desperdicio",
        name="Mermas y desperdicio",
        icon="♻️",
        category="Finanzas operativas",
        summary="Registra pérdidas operativas para medir el impacto real de errores y fallas de producción.",
        capabilities=(
            "Errores de impresión",
            "Materiales dañados",
            "Fallas de producción",
            "Desperdicio CMYK",
        ),
        integrations=("Producción", "Inventario", "Costeo industrial", "Auditoría"),
        business_value="Hace visible la utilidad perdida por desperdicio y mejora el control operacional.",
        priority="Alta",
    ),
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
        key="planificacion_produccion",
        name="Planificación de producción",
        icon="🗓️",
        category="Operación industrial",
        summary="Organiza trabajos por prioridad, capacidad y tiempos para evitar cuellos de botella.",
        capabilities=(
            "Ordenar trabajos por prioridad",
            "Asignar tiempos",
            "Evitar cuellos de botella",
            "Calendarizar producción",
        ),
        integrations=("Producción", "Activos", "Rutas", "Cotizaciones"),
        business_value="Mejora promesas de entrega, uso de capacidad y secuenciación de órdenes.",
        priority="Alta",
    ),
    ModuleBlueprint(
        key="control_calidad",
        name="Control de calidad",
        icon="✅",
        category="Operación industrial",
        summary="Registra calidad, no conformidades y reprocesos antes de entregar al cliente.",
        capabilities=(
            "Productos defectuosos",
            "Reprocesos",
            "Validaciones antes de entrega",
        ),
        integrations=("Producción", "Clientes", "Mermas", "Auditoría"),
        business_value="Protege reputación, reduce devoluciones y cuantifica el costo de la mala calidad.",
        priority="Media-Alta",
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
    ModuleBlueprint(
        key="contabilidad",
        name="Contabilidad",
        icon="📚",
        category="Contabilidad",
        summary="Formaliza la capa contable con libros, balances y estados financieros.",
        capabilities=(
            "Libro diario",
            "Libro mayor",
            "Balances",
            "Estados financieros",
        ),
        integrations=("Ventas", "Gastos", "CxC", "CxP", "Impuestos"),
        business_value="Permite cerrar mes, auditar la operación y llevar el ERP a un nivel contable real.",
        priority="Crítica",
    ),
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
    ModuleBlueprint(
        key="catalogo",
        name="Catálogo",
        icon="🛍️",
        category="Negocio y crecimiento",
        summary="Publica productos, servicios y paquetes para canales digitales como WhatsApp e Instagram.",
        capabilities=(
            "Productos",
            "Precios",
            "Servicios",
            "Paquetes",
        ),
        integrations=("Ventas", "CRM", "Marketing", "Cotizaciones"),
        business_value="Simplifica la venta digital y la presentación comercial del portafolio.",
        priority="Media",
    ),
    ModuleBlueprint(
        key="rrhh",
        name="RRHH",
        icon="👨‍💼",
        category="Administración interna",
        summary="Centraliza empleados, roles operativos, asistencia y comisiones.",
        capabilities=(
            "Usuarios / empleados",
            "Roles",
            "Asistencia",
            "Comisiones",
        ),
        integrations=("Seguridad", "Ventas", "Producción", "Auditoría"),
        business_value="Ordena la operación interna y facilita medir productividad y pago variable.",
        priority="Media",
    ),
    ModuleBlueprint(
        key="seguridad_roles",
        name="Seguridad / Roles",
        icon="🔐",
        category="Administración interna",
        summary="Amplía el control de permisos por módulo, proceso y nivel de riesgo.",
        capabilities=(
            "Perfiles avanzados",
            "Permisos por módulo",
            "Restricciones por acción crítica",
        ),
        integrations=("RRHH", "Auditoría", "Configuración"),
        business_value="Protege datos sensibles y reduce errores humanos en procesos críticos.",
        priority="Alta",
    ),
    ModuleBlueprint(
        key="manuales_sop",
        name="Manuales / SOP",
        icon="📘",
        category="Administración interna",
        summary="Formaliza procedimientos, instructivos y conocimiento operativo dentro del ERP.",
        capabilities=(
            "Manuales internos",
            "Procedimientos estándar",
            "Versionado documental",
        ),
        integrations=("RRHH", "Calidad", "Activos", "Producción"),
        business_value="Reduce dependencia del conocimiento informal y mejora entrenamiento del personal.",
        priority="Media",
    ),
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
    "finanzas": (
        "compras_proveedores",
        "cuentas_por_pagar",
        "tesoreria",
        "costeo_industrial",
        "mermas_desperdicio",
    ),
    "industrial": (
        "mantenimiento_activos",
        "planificacion_produccion",
        "control_calidad",
        "rutas_produccion",
    ),
    "contable": (
        "contabilidad",
        "impuestos",
        "conciliacion_bancaria",
    ),
    "growth": (
        "crm",
        "marketing_ventas",
        "fidelizacion",
        "catalogo",
    ),
    "admin": (
        "rrhh",
        "seguridad_roles",
        "manuales_sop",
    ),
}


def _render_module(module: ModuleBlueprint) -> None:
    st.subheader(f"{module.icon} {module.name}")
    st.caption(f"{module.category} · Prioridad {module.priority}")
    st.info(module.summary)

    left, right = st.columns((1.4, 1))
    with left:
        st.markdown("### Alcance funcional")
        for capability in module.capabilities:
            st.markdown(f"- {capability}")

    with right:
        st.markdown("### Conecta con")
        for integration in module.integrations:
            st.markdown(f"- {integration}")
        st.markdown("### Valor de negocio")
        st.write(module.business_value)



def render_module_blueprint(module_key: str, usuario: str | None = None) -> None:
    module = MODULE_BY_KEY[module_key]
    st.markdown(f"## {module.icon} {module.name}")
    if usuario:
        st.caption(f"Vista estratégica para {usuario}")
    st.write(module.summary)

    metric_1, metric_2, metric_3 = st.columns(3)
    metric_1.metric("Capacidades clave", len(module.capabilities))
    metric_2.metric("Integraciones", len(module.integrations))
    metric_3.metric("Prioridad", module.priority)

    tab1, tab2, tab3 = st.tabs(["📌 Definición", "🔗 Integraciones", "🚀 Implementación"])
    with tab1:
        st.markdown("### Debe incluir")
        for capability in module.capabilities:
            st.markdown(f"- {capability}")
        st.success(module.business_value)

    with tab2:
        st.markdown("### Sistemas conectados")
        for integration in module.integrations:
            st.markdown(f"- {integration}")
        st.caption(
            "Estos módulos fueron agregados como blueprint funcional para extender el ERP sin perder trazabilidad entre finanzas, producción y operación."
        )

    with tab3:
        st.markdown("### Siguiente fase recomendada")
        st.markdown(
            "1. Definir tablas y eventos transaccionales.\n"
            "2. Construir servicios de dominio y reglas de negocio.\n"
            "3. Crear formularios, reportes y tableros operativos.\n"
            "4. Conectar métricas al dashboard ejecutivo."
        )
        st.warning("Blueprint listo para priorización funcional y técnica.")



def render_module_portfolio(usuario: str | None = None) -> None:
    st.subheader("🧩 Portafolio de módulos ERP propuestos")
    if usuario:
        st.caption(f"Mapa de expansión solicitado para {usuario}.")
    st.write(
        "Se incorporó un portafolio de 19 módulos estratégicos para cubrir finanzas operativas, operación industrial, contabilidad, crecimiento y administración interna."
    )

    total_modules = len(MODULE_BLUEPRINTS)
    total_capabilities = sum(len(module.capabilities) for module in MODULE_BLUEPRINTS)
    high_priority = sum(module.priority in {"Crítica", "Alta"} for module in MODULE_BLUEPRINTS)

    m1, m2, m3 = st.columns(3)
    m1.metric("Módulos nuevos", total_modules)
    m2.metric("Capacidades definidas", total_capabilities)
    m3.metric("Prioridad alta/crítica", high_priority)

    for category_key, module_keys in CATEGORY_KEYS.items():
        with st.expander(CATEGORY_LABELS[category_key], expanded=True):
            for module_key in module_keys:
                _render_module(MODULE_BY_KEY[module_key])
                st.divider()

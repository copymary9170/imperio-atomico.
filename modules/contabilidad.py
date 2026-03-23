from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class AccountingCapability:
    title: str
    description: str
    outputs: tuple[str, ...]


@dataclass(frozen=True)
class AccountingTable:
    name: str
    purpose: str
    key_fields: tuple[str, ...]


@dataclass(frozen=True)
class AccountingFlow:
    source: str
    accounting_result: str
    control: str


ACCOUNTING_CAPABILITIES: tuple[AccountingCapability, ...] = (
    AccountingCapability(
        title="Motor contable",
        description="Centraliza el registro de asientos con validaciones mínimas para mantener consistencia entre origen, comprobante y periodo.",
        outputs=(
            "Libro diario",
            "Libro mayor",
            "Pólizas por origen",
        ),
    ),
    AccountingCapability(
        title="Cierre y balances",
        description="Prepara el cierre mensual con conciliación de saldos, reclasificaciones y vistas ejecutivas para revisión.",
        outputs=(
            "Balanza de comprobación",
            "Estado de resultados",
            "Balance general",
        ),
    ),
    AccountingCapability(
        title="Control tributario",
        description="Conecta IVA, retenciones e impuestos con las operaciones para disminuir retrabajos al momento de declarar.",
        outputs=(
            "Resumen de IVA",
            "Base imponible",
@@ -59,110 +73,216 @@ ACCOUNTING_INTEGRATIONS: tuple[str, ...] = (
    "Cuentas por pagar",
    "Impuestos",
    "Conciliación bancaria",
    "Auditoría",
)

IMPLEMENTATION_PHASES: tuple[tuple[str, str], ...] = (
    (
        "Fase 1 · Base contable",
        "Definir catálogo de cuentas, periodos, asientos, pólizas y reglas de origen para las transacciones existentes.",
    ),
    (
        "Fase 2 · Automatización",
        "Mapear ventas, gastos, compras y movimientos de caja para generar asientos sugeridos y validar descuadres.",
    ),
    (
        "Fase 3 · Reportes",
        "Liberar balanza, estado de resultados, balance general y auxiliares por cuenta con filtros por periodo.",
    ),
    (
        "Fase 4 · Cierre y cumplimiento",
        "Agregar cierre mensual, validaciones de periodos, integración fiscal y evidencias para auditoría interna.",
    ),
)

ACCOUNTING_TABLES: tuple[AccountingTable, ...] = (
    AccountingTable(
        name="conta_catalogo_cuentas",
        purpose="Catálogo jerárquico para clasificar activos, pasivos, patrimonio, ingresos, costos y gastos.",
        key_fields=("codigo", "nombre", "tipo", "naturaleza", "cuenta_padre_id", "acepta_movimientos"),
    ),
    AccountingTable(
        name="conta_periodos",
        purpose="Controla aperturas, cierres y bloqueos por periodo contable.",
        key_fields=("periodo", "fecha_inicio", "fecha_fin", "estado", "cerrado_por", "cerrado_en"),
    ),
    AccountingTable(
        name="conta_polizas",
        purpose="Agrupa asientos por origen, tipo de comprobante y lote operativo.",
        key_fields=("numero", "origen", "fecha", "periodo", "estado", "referencia_externa"),
    ),
    AccountingTable(
        name="conta_asientos",
        purpose="Cabecera del asiento con contexto contable y validación del balance débito/crédito.",
        key_fields=("poliza_id", "comprobante", "descripcion", "total_debito", "total_credito", "origen_modelo"),
    ),
    AccountingTable(
        name="conta_movimientos",
        purpose="Detalle por cuenta contable para libro diario, mayor y balances.",
        key_fields=("asiento_id", "cuenta_id", "debito", "credito", "centro_costo", "tercero_id"),
    ),
    AccountingTable(
        name="conta_reglas_origen",
        purpose="Mapea cada transacción operativa con sus reglas de contabilización y validaciones.",
        key_fields=("origen", "evento", "cuenta_debito", "cuenta_credito", "condicion", "prioridad"),
    ),
    AccountingTable(
        name="conta_impuestos",
        purpose="Relaciona IVA, retenciones y bases imponibles con documentos y asientos.",
        key_fields=("documento_tipo", "tasa", "base_imponible", "impuesto", "asiento_id", "vencimiento"),
    ),
    AccountingTable(
        name="conta_auditoria",
        purpose="Bitácora para rastrear cambios, reclasificaciones y diferencias detectadas.",
        key_fields=("entidad", "entidad_id", "accion", "usuario", "fecha", "detalle"),
    ),
)

ACCOUNTING_FLOWS: tuple[AccountingFlow, ...] = (
    AccountingFlow(
        source="Ventas",
        accounting_result="Reconoce ingresos, impuestos trasladados y cuentas por cobrar o entradas a caja.",
        control="Validar serie, cliente, impuesto y periodo abierto antes de contabilizar.",
    ),
    AccountingFlow(
        source="Gastos",
        accounting_result="Registra gasto, IVA acreditable, retenciones y obligación de pago.",
        control="Exigir documento soporte, centro de costo y proveedor relacionado.",
    ),
    AccountingFlow(
        source="Compras / CxP",
        accounting_result="Capitaliza inventario o gasto y deja trazabilidad contra facturas y vencimientos.",
        control="Cruzar factura, recepción y saldo pendiente para evitar duplicados.",
    ),
    AccountingFlow(
        source="Caja / Tesorería",
        accounting_result="Aplica cobros, pagos, anticipos y movimientos internos con impacto en bancos y caja.",
        control="Conciliar contra movimientos bancarios y alertar diferencias de fecha o monto.",
    ),
    AccountingFlow(
        source="Impuestos",
        accounting_result="Consolida bases imponibles, IVA y retenciones para declaraciones y cierre fiscal.",
        control="Marcar vencimientos, estatus de declaración y evidencia documental.",
    ),
    AccountingFlow(
        source="Conciliación / Auditoría",
        accounting_result="Conecta diferencias con sus asientos, documentos y usuarios responsables.",
        control="Disparar alertas cuando cambie un asiento conciliado o un periodo cerrado.",
    ),
)

ACCOUNTING_PROBLEMS_TO_SOLVE: tuple[str, ...] = (
    "Traducir operaciones a asientos contables.",
    "Controlar periodos abiertos/cerrados.",
    "Preparar cierres mensuales y revisiones.",
    "Servir de base para impuestos y conciliación.",
)



def _render_overview(usuario: str | None) -> None:
    st.title("📚 Contabilidad")
    if usuario:
        st.caption(f"Módulo contable independiente para {usuario}")

    st.write(
        "Contabilidad ahora vive como módulo propio dentro del ERP para separar la capa financiera formal del portafolio de expansión y darle una hoja de ruta dedicada."
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Frentes contables", len(ACCOUNTING_CAPABILITIES))
    m2.metric("Integraciones", len(ACCOUNTING_INTEGRATIONS))
    m3.metric("Fases sugeridas", len(IMPLEMENTATION_PHASES))
    m4.metric("Prioridad", "Crítica")

    st.info(
        "Objetivo: consolidar libro diario, mayor, balances, estados financieros e integración fiscal sin depender del módulo de Nuevos módulos ERP."
    )



def _render_capabilities() -> None:
    st.markdown("### Alcance funcional")
    for capability in ACCOUNTING_CAPABILITIES:
        with st.container(border=True):
            st.markdown(f"#### {capability.title}")
            st.write(capability.description)
            st.markdown("**Entregables clave**")
            for output in capability.outputs:
                st.markdown(f"- {output}")



def _render_integrations() -> None:
    left, right = st.columns((1, 1))
    with left:
        st.markdown("### Integraciones críticas")
        for integration in ACCOUNTING_INTEGRATIONS:
            st.markdown(f"- {integration}")

    with right:
        st.markdown("### Qué debe resolver")
        for item in ACCOUNTING_PROBLEMS_TO_SOLVE:
            st.markdown(f"- {item}")
        st.success(
            "Separar Contabilidad permite priorizar arquitectura, reportes y cumplimiento sin mezclarlo con el backlog del portafolio ERP."
        )

    st.markdown("### Flujos transaccionales a contabilizar")
    for flow in ACCOUNTING_FLOWS:
        with st.container(border=True):
            st.markdown(f"**{flow.source}**")
            st.write(flow.accounting_result)
            st.caption(f"Control clave: {flow.control}")



def _render_data_model() -> None:
    st.markdown("### Modelo contable recomendado")
    st.write(
        "Siguiente paso recomendado: modelar tablas contables y enlazar cada origen transaccional con sus reglas de contabilización."
    )

    for table in ACCOUNTING_TABLES:
        with st.container(border=True):
            st.markdown(f"#### `{table.name}`")
            st.write(table.purpose)
            st.caption("Campos clave")
            st.code(", ".join(table.key_fields), language="text")



def _render_roadmap() -> None:
    st.markdown("### Hoja de ruta sugerida")
    for phase, description in IMPLEMENTATION_PHASES:
        with st.container(border=True):
            st.markdown(f"**{phase}**")
            st.write(description)

    st.warning(
        "Siguiente paso recomendado: modelar tablas contables y enlazar cada origen transaccional con sus reglas de contabilización."
    )



def render_contabilidad_dashboard(usuario: str | None = None) -> None:
    _render_overview(usuario)

    tab1, tab2, tab3, tab4 = st.tabs([
        "📒 Alcance",
        "🔗 Integraciones",
        "🗃️ Modelo de datos",
        "🚀 Implementación",
    ])

    with tab1:
        _render_capabilities()

    with tab2:
        _render_integrations()

    with tab3:
        _render_data_model()

    with tab4:
        _render_roadmap()

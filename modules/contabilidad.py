from __future__ import annotations

from dataclasses import dataclass

import streamlit as st


@dataclass(frozen=True)
class AccountingCapability:
    title: str
    description: str
    outputs: tuple[str, ...]


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
            "Calendario fiscal",
        ),
    ),
    AccountingCapability(
        title="Auditoría y trazabilidad",
        description="Relaciona cada asiento con ventas, gastos, compras, tesorería y conciliación bancaria para soportar revisiones.",
        outputs=(
            "Bitácora contable",
            "Rastreo por documento",
            "Alertas de diferencias",
        ),
    ),
)

ACCOUNTING_INTEGRATIONS: tuple[str, ...] = (
    "Ventas",
    "Gastos",
    "Caja",
    "Tesorería",
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
        st.markdown(
            "- Traducir operaciones a asientos contables.\n"
            "- Controlar periodos abiertos/cerrados.\n"
            "- Preparar cierres mensuales y revisiones.\n"
            "- Servir de base para impuestos y conciliación."
        )
        st.success(
            "Separar Contabilidad permite priorizar arquitectura, reportes y cumplimiento sin mezclarlo con el backlog del portafolio ERP."
        )



def _render_roadmap() -> None:
    st.markdown("### Hoja de ruta sugerida")
    for phase, description in IMPLEMENTATION_PHASES:
        st.markdown(f"**{phase}**")
        st.write(description)

    st.warning(
        "Siguiente paso recomendado: modelar tablas contables y enlazar cada origen transaccional con sus reglas de contabilización."
    )



def render_contabilidad_dashboard(usuario: str | None = None) -> None:
    _render_overview(usuario)

    tab1, tab2, tab3 = st.tabs([
        "📒 Estructura",
        "🔗 Integraciones",
        "🚀 Implementación",
    ])

    with tab1:
        _render_capabilities()

    with tab2:
        _render_integrations()

    with tab3:
        _render_roadmap()
